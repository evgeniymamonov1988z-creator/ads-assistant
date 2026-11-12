from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List

import httpx

from ..config import settings
from ..models import CampaignStat, CampaignStatPeriods, MutationChange, PeriodStats
from .base import AdsApiError, Provider
from .http import LimitedHttp, network_error_text

GOOGLE_ERROR_HINTS = {
    "AUTHORIZATION_ERROR": "Google Ads отклонил доступ: проверьте client_id/secret и что вход выполнен тем аккаунтом, у которого есть доступ к рекламе.",
    "DEVELOPER_TOKEN_NOT_APPROVED": "Developer token в режиме «тест»: работают только тестовые аккаунты. Подайте заявку на Basic access в API Center.",
    "DEVELOPER_TOKEN_PROHIBITED": "Developer token запрещён для этого аккаунта — проверьте настройку токена и MCC.",
    "CUSTOMER_NOT_ENABLED": "Рекламный аккаунт Google Ads отключён или не активирован.",
    "USER_PERMISSION_DENIED": "У пользователя нет прав на этот аккаунт Google Ads. Проверьте доступ через управляющий аккаунт (MCC).",
    "QUOTA_ERROR": "Исчерпана квота Google Ads API на сегодня. Подождите до сброса квоты или запросите повышение.",
    "RESOURCE_EXHAUSTED": "Google ограничил частоту запросов. Сделайте паузу и повторите.",
    "INVALID_CUSTOMER_ID": "Неверный идентификатор рекламного аккаунта Google Ads.",
}

GAQL_CAMPAIGN_METRICS = """
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  campaign_budget.amount_micros,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions
FROM campaign
WHERE segments.date BETWEEN '{dfrom}' AND '{dto}'
"""

GAQL_CAMPAIGNS = """
SELECT campaign.id, campaign.name, campaign.status, campaign_budget.amount_micros
FROM campaign
WHERE campaign.status != 'REMOVED'
"""


class GoogleAdsProvider(Provider):
    name = "google"

    def __init__(self) -> None:
        self.http = LimitedHttp(timeout=settings.request_timeout)

    def _check_configured(self) -> None:
        if not settings.google_configured:
            raise AdsApiError(
                "Google Ads не настроен: задайте GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_CLIENT_ID/SECRET и GOOGLE_REFRESH_TOKEN.",
                code="NOT_CONFIGURED",
            )
        if not settings.gads_customer_id:
            raise AdsApiError("Не задан идентификатор рекламного аккаунта Google Ads (GOOGLE_CUSTOMER_ID).", code="NOT_CONFIGURED")

    async def _access_token(self) -> str:
        try:
            data = await self.http.json(
                "POST",
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.gads_client_id,
                    "client_secret": settings.gads_client_secret,
                    "refresh_token": settings.gads_refresh_token,
                },
            )
        except AdsApiError as exc:
            raise AdsApiError(exc.message, code=exc.code) from exc
        if data.get("status_code", 200) >= 400 or not data.get("access_token"):
            err = data.get("error_description") or data.get("error") or "нет access_token"
            raise AdsApiError(
                f"Не удалось обновить токен Google ({err}). Перевыпустите refresh token.", code="AUTH"
            )
        return data["access_token"]

    def _headers(self, token: str) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "developer-token": settings.gads_developer_token,
            "Content-Type": "application/json",
        }
        if settings.gads_login_customer_id:
            headers["login-customer-id"] = settings.gads_login_customer_id.replace("-", "")
        return headers

    async def _search(self, query: str) -> List[Dict[str, Any]]:
        self._check_configured()
        token = await self._access_token()
        customer = settings.gads_customer_id.replace("-", "")
        url = f"https://googleads.googleapis.com/{settings.gads_api_version}/customers/{customer}/googleAds:search"
        try:
            resp = await self.http.json("POST", url, headers=self._headers(token), data=json.dumps({"query": query}).encode())
        except AdsApiError as exc:
            raise AdsApiError(exc.message, code=exc.code) from exc

        status = int(resp.get("status_code") or 0)
        if status == 401:
            raise AdsApiError("Google Ads отклонил токен. Перевыпустите refresh token.", code="AUTH")
        if status == 403:
            msg = json.dumps(resp.get("error") or resp, ensure_ascii=False)[:600]
            raise AdsApiError(explain_google_error(msg), code="AUTH")
        if status == 429:
            raise AdsApiError("Google ограничил частоту запросов (лимит). Повторите через несколько минут.", code="RATE_LIMIT")
        if status >= 400:
            msg = json.dumps(resp.get("error") or resp, ensure_ascii=False)[:600]
            raise AdsApiError(explain_google_error(msg), code=f"GOOGLE_{status}")

        results = resp.get("results") or []
        next_token = resp.get("nextPageToken")
        pages = 0
        while next_token and pages < 20:
            pages += 1
            resp2 = await self.http.json(
                "POST",
                url,
                headers=self._headers(token),
                data=json.dumps({"query": query, "pageToken": next_token}).encode(),
            )
            results.extend(resp2.get("results") or [])
            next_token = resp2.get("nextPageToken")
        return results

    async def fetch_stats(self, date_from: date, date_to: date) -> List[CampaignStatPeriods]:
        base = await self._search(GAQL_CAMPAIGNS)
        meta: Dict[str, Dict[str, Any]] = {}
        for row in base:
            c = row.get("campaign") or {}
            b = row.get("campaignBudget") or {}
            meta[str(c.get("id"))] = {
                "name": c.get("name"),
                "status": c.get("status"),
                "budget": micros_to_money(b.get("amountMicros")),
            }

        rows7 = await self._search(GAQL_CAMPAIGN_METRICS.format(dfrom=date_from.isoformat(), dto=date_to.isoformat()))
        rows1 = await self._search(
            GAQL_CAMPAIGN_METRICS.format(dfrom=date_to.isoformat(), dto=date_to.isoformat())
        )
        agg7 = aggregate_google(rows7)
        agg1 = aggregate_google(rows1)

        out: List[CampaignStatPeriods] = []
        ids = list(dict.fromkeys(list(meta.keys()) + list(agg7.keys())))
        for cid in ids:
            m = meta.get(cid, {})
            a7 = agg7.get(cid, {})
            a1 = agg1.get(cid, {})
            stat = CampaignStat(
                id=cid,
                name=m.get("name") or a7.get("name") or cid,
                source="google",
                impressions=a7.get("impressions", 0),
                clicks=a7.get("clicks", 0),
                cost=a7.get("cost", 0.0),
                conversions=a7.get("conversions", 0.0),
                daily_budget=m.get("budget"),
                status=str(m.get("status") or "ENABLED"),
            )
            out.append(
                CampaignStatPeriods(
                    campaign=stat,
                    last7=period(a7, date_from, date_to, 7),
                    lastDay=period(a1, date_to, date_to, 1),
                )
            )
        return out

    async def search_term_report(self, date_from: date, date_to: date, campaign_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        query = f"""
SELECT campaign.id, campaign.name, ad_group.id, search_term_view.search_term, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
FROM search_term_view
WHERE segments.date BETWEEN '{date_from:%Y-%m-%d}' AND '{date_to:%Y-%m-%d}'
  AND campaign.id = {int(campaign_id)}
ORDER BY metrics.cost_micros DESC
LIMIT {limit}
"""
        rows = await self._search(query)
        out = []
        for r in rows:
            st = r.get("searchTermView") or {}
            m = r.get("metrics") or {}
            ag = r.get("adGroup") or {}
            out.append(
                {
                    "term": st.get("searchTerm"),
                    "adgroup_id": str(ag.get("id") or ""),
                    "clicks": int(float(m.get("clicks") or 0)),
                    "impressions": int(float(m.get("impressions") or 0)),
                    "cost": micros_to_money(m.get("costMicros")),
                    "conversions": float(m.get("conversions") or 0),
                }
            )
        return out

    async def apply_changes(self, changes: List[MutationChange]) -> List[MutationChange]:
        self._check_configured()
        token = await self._access_token()
        customer = settings.gads_customer_id.replace("-", "")
        ops: List[Dict[str, Any]] = []
        for change in changes:
            if change.field == "daily_budget":
                ops.append(
                    {
                        "campaignBudgetOperation": {
                            "update": {
                                "resourceName": change.payload.get("budget_resource")
                                or f"customers/{customer}/campaignBudgets/{change.entity_id}",
                                "amountMicros": str(int(round(float(change.after) * 1_000_000))),
                            },
                            "updateMask": "amount_micros",
                        }
                    }
                )
            elif change.field == "bid":
                ops.append(
                    {
                        "adGroupCriterionOperation": {
                            "update": {
                                "resourceName": change.payload.get("criterion_resource")
                                or change.entity_id,
                                "cpcBidMicros": str(int(round(float(change.after) * 1_000_000))),
                            },
                            "updateMask": "cpc_bid_micros",
                        }
                    }
                )
            else:
                raise AdsApiError(
                    "Для Google Ads в этой версии поддерживаются изменения ставок и бюджетов; минус-слова добавляйте через Яндекс токен.",
                    code="UNSUPPORTED",
                )

        endpoint = f"https://googleads.googleapis.com/{settings.gads_api_version}/customers/{customer}/googleAds:mutate"
        payload = {"mutateOperations": ops}
        resp = await self.http.json(
            "POST", endpoint, headers=self._headers(token), data=json.dumps(payload).encode()
        )
        status = int(resp.get("status_code") or 0)
        if status >= 400:
            msg = json.dumps(resp.get("error") or resp, ensure_ascii=False)[:600]
            raise AdsApiError(explain_google_error(msg), code=f"GOOGLE_{status}")
        return changes

    async def health(self) -> dict:
        if not settings.google_configured:
            return {"source": "google", "ok": False, "message": "Google Ads: не заданы developer token / refresh token"}
        try:
            rows = await self._search("SELECT customer.id, customer.descriptive_name FROM customer LIMIT 1")
            name = (rows[0].get("customer") or {}).get("descriptiveName") if rows else ""
            return {"source": "google", "ok": True, "message": f"Google Ads доступен{f' ({name})' if name else ''}"}
        except AdsApiError as exc:
            return {"source": "google", "ok": False, "message": exc.message}


def explain_google_error(raw: str) -> str:
    for key, text in GOOGLE_ERROR_HINTS.items():
        if key in raw:
            return text
    return f"Google Ads вернул ошибку: {raw[:300]}"


def micros_to_money(value: Any) -> float:
    try:
        return round(float(value) / 1_000_000, 2)
    except Exception:
        return 0.0


def aggregate_google(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        camp = row.get("campaign") or {}
        m = row.get("metrics") or {}
        cid = str(camp.get("id") or "")
        if not cid:
            continue
        item = out.setdefault(cid, {"name": camp.get("name"), "impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
        item["impressions"] += int(float(m.get("impressions") or 0))
        item["clicks"] += int(float(m.get("clicks") or 0))
        item["cost"] += micros_to_money(m.get("costMicros"))
        item["conversions"] += float(m.get("conversions") or 0)
    return out


def period(agg: Dict[str, Any], dfrom: date, dto: date, days: int) -> PeriodStats:
    return PeriodStats(
        label=f"{days} дн.",
        date_from=dfrom,
        date_to=dto,
        impressions=agg.get("impressions", 0),
        clicks=agg.get("clicks", 0),
        cost=round(float(agg.get("cost", 0.0)), 2),
        conversions=round(float(agg.get("conversions", 0.0)), 2),
        days=days,
    )
