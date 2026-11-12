from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict, List

from ..config import settings
from ..models import CampaignStat, CampaignStatPeriods, MutationChange, PeriodStats
from .base import AdsApiError, Provider
from .http import LimitedHttp

# Коды ошибок Yandex Direct, которые полезно объяснить по-русски
ERROR_HINTS = {
    53: "Доступ к Яндекс Директу запрещён. Проверьте права токена и логин клиента.",
    506: "Директ вернул внутреннюю ошибку сервиса. Повторите запрос позже.",
    8000: "Запрос не принят Яндексом — вероятно, превышены лимиты баллов. Попробуйте позже.",
    8800: "Превышено допустимое число объектов в одном запросе.",
    4000: "Слишком много обращений к Директу подряд. Подождите минуту и повторите.",
    5002: "Отчёт ещё не сформирован или номер отчёта неверный.",
}

PERIOD_FIELDS = ["CampaignId", "CampaignName", "Impressions", "Clicks", "Cost", "Conversions"]


class YandexProvider(Provider):
    name = "yandex"
    base: str = "direct"  # direct | sandbox (используется в демо-режиме)

    def __init__(self) -> None:
        self.http = LimitedHttp(timeout=settings.request_timeout)

    def _base_url(self, service: str) -> str:
        root = settings.yd_api_url.rstrip("/")
        if self.base == "sandbox":
            root = root.replace("api.direct.yandex.com", "api-sandbox.direct.yandex.com")
        return f"{root}/{service}"

    def _headers(self, *, money_units: bool = False) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Language": settings.yd_api_lang,
            "returnMoneyInMicros": "false" if money_units else "true",
        }
        if settings.yd_agency_client_login:
            headers["Client-Login"] = settings.yd_agency_client_login
        return headers

    def _token(self) -> str:
        if not settings.yandex_configured:
            raise AdsApiError(
                "Яндекс Директ не настроен: не задан OAuth-токен в переменных окружения.", code="NOT_CONFIGURED"
            )
        return settings.yd_oauth_token or settings.yd_refresh_token

    async def _call(self, service: str, payload: Dict[str, Any], *, units: bool = False) -> Dict[str, Any]:
        resp = await self.http.json(
            "POST",
            self._base_url(service),
            headers={**self._headers(money_units=units), "ProcessingMode": "auto"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
        status = int(resp.get("status_code") or 0)
        if status in (401, 403):
            raise AdsApiError(
                "Яндекс отклонил доступ. Проверьте, что OAuth-токен действует и у него есть права на этот аккаунт.",
                code="AUTH",
            )
        if status == 429:
            raise AdsApiError("Яндекс ограничил частоту запросов. Подождите минуту и повторите.", code="RATE_LIMIT")
        if status >= 400 and resp.get("raw_text") and not resp.get("error"):
            raise AdsApiError(f"Яндекс вернул ошибку HTTP {status}: {str(resp['raw_text'])[:300]}", code=f"HTTP_{status}")
        error = resp.get("error") or {}
        if error:
            code = error.get("error_code")
            detail = error.get("error_detail") or error.get("error_string") or "без описания"
            raise AdsApiError(ERROR_HINTS.get(code, f"Яндекс Директ вернул ошибку: {detail}"), code=f"YD_{code}")
        return resp.get("result") or {}

    async def _campaigns(self) -> Dict[str, Dict[str, Any]]:
        result = await self._call(
            "campaigns",
            {
                "method": "get",
                "params": {
                    "SelectionCriteria": {},
                    "FieldNames": ["Id", "Name", "State", "Status", "DailyBudget", "Type"],
                },
            },
        )
        return {str(c.get("Id")): c for c in result.get("Campaigns") or []}

    async def _report(self, date_from: date, date_to: date) -> List[Dict[str, str]]:
        body = {
            "params": {
                "SelectionCriteria": {"DateFrom": date_from.isoformat(), "DateTo": date_to.isoformat()},
                "FieldNames": PERIOD_FIELDS,
                "ReportName": f"adassistant_{date_from:%Y%m%d}_{date_to:%Y%m%d}",
                "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
                "DateRangeType": "CUSTOM_DATE",
                "Format": "TSV",
                "IncludeVAT": "YES",
                "IncludeDiscount": "NO",
            }
        }
        headers = {
            **self._headers(money_units=True),
            "processingMode": "auto",
            "skipReportHeader": "true",
            "skipReportSummary": "true",
        }
        resp = await self.http.json(
            "POST", self._base_url("reports"), headers=headers, data=json.dumps(body, ensure_ascii=False).encode("utf-8")
        )
        status = int(resp.get("status_code") or 0)
        if status == 4000:
            raise AdsApiError(
                "Директ ограничил частоту формирования отчётов. Подождите пару минут — данные не потеряются.",
                code="RATE_LIMIT",
            )
        if status >= 400:
            if resp.get("raw_text"):
                raise AdsApiError(f"Не удалось получить отчёт Директа: {str(resp['raw_text'])[:300]}", code="REPORT")
            raise AdsApiError("Не удалось получить отчёт Директа. Попробуйте позже.", code="REPORT")
        return parse_tsv(resp.get("raw_text") or "")

    async def fetch_stats(self, date_from: date, date_to: date) -> List[CampaignStatPeriods]:
        campaigns = await self._campaigns()
        last7_rows = await self._report(date_from, date_to)
        day_rows = await self._report(date_to, date_to)
        by7 = aggregate(last7_rows)
        by1 = aggregate(day_rows)

        out: List[CampaignStatPeriods] = []
        for cid in list(dict.fromkeys(list(campaigns.keys()) + list(by7.keys()))):
            meta = campaigns.get(cid, {})
            a7 = by7.get(cid, {})
            a1 = by1.get(cid, {})
            out.append(
                CampaignStatPeriods(
                    campaign=CampaignStat(
                        id=cid,
                        name=meta.get("Name") or a7.get("name") or cid,
                        source="yandex",
                        impressions=a7.get("impressions", 0),
                        clicks=a7.get("clicks", 0),
                        cost=a7.get("cost", 0.0),
                        conversions=a7.get("conversions", 0.0),
                        daily_budget=daily_budget(meta),
                        status=str(meta.get("State") or "ENABLED"),
                    ),
                    last7=period(a7, date_from, date_to, 7),
                    lastDay=period(a1, date_to, date_to, 1),
                )
            )
        return out

    async def keywords(self, campaign_id: str) -> List[Dict[str, Any]]:
        result = await self._call(
            "keywords",
            {
                "method": "get",
                "params": {
                    "SelectionCriteria": {"CampaignIds": [int(campaign_id)]},
                    "FieldNames": ["Id", "Keyword", "AdGroupId", "Bid", "State"],
                },
            },
        )
        return result.get("Keywords") or []

    async def search_terms(self, campaign_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Поисковые запросы кампании по расходу (для сбора минус-слов)."""
        dto = date.today() - timedelta(days=1)
        dfrom = dto - timedelta(days=max(1, days) - 1)
        body = {
            "params": {
                "SelectionCriteria": {
                    "DateFrom": dfrom.isoformat(),
                    "DateTo": dto.isoformat(),
                    "Filter": [{"Field": "CampaignId", "Operator": "EQUALS", "Values": [str(campaign_id)]}],
                },
                "FieldNames": ["Query", "CampaignId", "AdGroupId", "Impressions", "Clicks", "Cost", "Conversions"],
                "ReportName": f"adassistant_st_{campaign_id}_{dfrom:%Y%m%d}",
                "ReportType": "SEARCH_QUERY_PERFORMANCE_REPORT",
                "DateRangeType": "CUSTOM_DATE",
                "Format": "TSV",
                "IncludeVAT": "YES",
            }
        }
        headers = {
            **self._headers(money_units=True),
            "processingMode": "auto",
            "skipReportHeader": "true",
            "skipReportSummary": "true",
        }
        resp = await self.http.json(
            "POST", self._base_url("reports"), headers=headers, data=json.dumps(body, ensure_ascii=False).encode("utf-8")
        )
        if int(resp.get("status_code") or 0) >= 400 and resp.get("raw_text"):
            raise AdsApiError(f"Не удалось получить поисковые запросы: {str(resp['raw_text'])[:200]}", code="REPORT")
        rows = parse_tsv(resp.get("raw_text") or "")
        return [
            {
                "term": r.get("Query"),
                "adgroup_id": str(r.get("AdGroupId") or ""),
                "clicks": to_int(r.get("Clicks")),
                "impressions": to_int(r.get("Impressions")),
                "cost": micros_to_money(r.get("Cost")),
                "conversions": to_float(r.get("Conversions")),
            }
            for r in rows
        ]

    async def apply_changes(self, changes: List[MutationChange]) -> List[MutationChange]:
        applied: List[MutationChange] = []
        for change in changes:
            if change.field == "bid":
                keyword_id = int(change.payload.get("keyword_id") or change.entity_id)
                micros = int(round(float(change.payload.get("bid_raw_after") or strip_money(change.after)) * 1_000_000))
                res = await self._call(
                    "keywords", {"method": "setBids", "params": {"Bids": [{"KeywordId": keyword_id, "Bid": micros}]}}
                )
                failed = [r for r in res.get("SetBidsResults") or [] if r.get("Errors")]
                if failed:
                    raise AdsApiError("Директ не принял ставку: " + describe_errors(failed[0]), code="BID_FAILED")
            elif change.field == "daily_budget":
                micros = int(round(float(change.payload.get("budget_raw_after") or strip_money(change.after)) * 1_000_000))
                res = await self._call(
                    "campaigns",
                    {
                        "method": "update",
                        "params": {
                            "Campaigns": [
                                {"Id": int(change.entity_id), "DailyBudget": {"Amount": micros, "Mode": "STANDARD"}}
                            ]
                        },
                    },
                )
                failed = [r for r in res.get("UpdateResults") or [] if r.get("Errors")]
                if failed:
                    raise AdsApiError(
                        "Директ не принял бюджет кампании: " + describe_errors(failed[0]), code="BUDGET_FAILED"
                    )
            elif change.field == "minus_words":
                words = [w.strip() for w in str(change.after).split(",") if w.strip()]
                adgroup_id = int(change.payload.get("adgroup_id") or change.entity_id)
                res = await self._call(
                    "adgroups",
                    {
                        "method": "update",
                        "params": {"AdGroups": [{"Id": adgroup_id, "NegativeKeywords": {"Items": list(dict.fromkeys(words))[:4000]}}]},
                    },
                )
                failed = [r for r in res.get("UpdateResults") or [] if r.get("Errors")]
                if failed:
                    raise AdsApiError(
                        "Директ не принял минус-слова: " + describe_errors(failed[0]), code="MINUS_FAILED"
                    )
            else:
                raise AdsApiError(f"Неизвестный тип изменения: {change.field}", code="BAD_CHANGE")
            applied.append(change)
        return applied

    async def health(self) -> dict:
        if not settings.yandex_configured:
            return {"source": "yandex", "ok": False, "message": "Яндекс Директ: не задан OAuth-токен"}
        try:
            campaigns = await self._campaigns()
            return {"source": "yandex", "ok": True, "message": f"Яндекс Директ доступен, кампаний: {len(campaigns)}"}
        except AdsApiError as exc:
            return {"source": "yandex", "ok": False, "message": exc.message}


def describe_errors(result: Dict[str, Any]) -> str:
    parts = []
    for err in (result.get("Errors") or [])[:3]:
        parts.append(ERROR_HINTS.get(err.get("Code"), err.get("Message") or err.get("Details") or "ошибка"))
    return "; ".join(parts) or "неизвестная ошибка"


def strip_money(text: str) -> str:
    keep = "".join(ch for ch in str(text) if ch.isdigit() or ch in ".,")
    return keep.replace(",", ".") or "0"


def micros_to_money(value: Any) -> float:
    try:
        return round(float(value) / 1_000_000, 2)
    except Exception:
        return 0.0


def to_int(value: Any) -> int:
    try:
        return int(float(str(value).replace(" ", "").replace(",", ".") or 0))
    except Exception:
        return 0


def to_float(value: Any) -> float:
    try:
        return float(str(value).replace(" ", "").replace(",", ".").replace("--", "0") or 0)
    except Exception:
        return 0.0


def daily_budget(meta: Dict[str, Any]) -> float | None:
    db = meta.get("DailyBudget") or {}
    if isinstance(db, dict) and db.get("Amount") is not None:
        return micros_to_money(db["Amount"])
    return None


def parse_tsv(text: str) -> List[Dict[str, str]]:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return []
    header = [h.strip().strip('"') for h in lines[0].split("\t")]
    rows: List[Dict[str, str]] = []
    for line in lines[1:]:
        cells = [c.strip().strip('"') for c in line.split("\t")]
        if len(cells) < len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def aggregate(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        cid = str(row.get("CampaignId") or "")
        if not cid:
            continue
        item = out.setdefault(
            cid, {"name": row.get("CampaignName") or "", "impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0}
        )
        item["impressions"] += to_int(row.get("Impressions"))
        item["clicks"] += to_int(row.get("Clicks"))
        item["cost"] += micros_to_money(row.get("Cost"))
        item["conversions"] += to_float(row.get("Conversions"))
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
