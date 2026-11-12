from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..config import settings
from ..models import (
    CampaignStatPeriods,
    KpiSettings,
    MutationChange,
    Priority,
    Recommendation,
)
from ..providers.base import AdsApiError, Provider

from .metrics import enrich, fmt_money

KIND_OVERRUN = "overrun"
KIND_CTR_LOW = "ctr_low"
KIND_CPA_HIGH = "cpa_high"
KIND_NO_CONVERSIONS = "no_conversions"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def rec_id(source: str, campaign_id: str, kind: str, suffix: str = "") -> str:
    raw = f"{source}|{campaign_id}|{kind}|{suffix}|{datetime.now(timezone.utc):%Y%m%d%H%M}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def priority_rank(p: Priority) -> int:
    return {"high": 0, "medium": 1, "low": 2}[p]


async def build_recommendations(
    campaigns: List[CampaignStatPeriods],
    kpi: KpiSettings,
    provider_factory,
    *,
    anomalies: List[str],
    warnings: List[str],
) -> List[Recommendation]:
    recs: List[Recommendation] = []
    currency = kpi.currency or settings.currency

    for item in campaigns:
        stat = item.campaign
        p7 = enrich(item.last7.model_copy())
        p1 = enrich(item.lastDay.model_copy())
        if p7.impressions == 0 and p1.impressions == 0:
            continue

        # --- 1. Перерасход дневного бюджета (последний день) ---
        budget = stat.daily_budget or kpi.daily_budget
        limit = budget * (1 + kpi.overrun_tolerance_pct / 100)
        if p1.cost > 0 and p1.cost > limit:
            overrun = p1.cost - budget
            anomalies.append(
                f"{stat.name}: расход за последний день {fmt_money(p1.cost, currency)} при бюджете "
                f"{fmt_money(budget, currency)} (+{round(p1.cost / max(budget, 0.01) * 100 - 100)}%)."
            )
            # цель: вернуть расход в рамки, но не ниже 50% текущего бюджета (иначе кампания «встанет»)
            new_budget = round(max(budget * 0.5, min(budget * 0.9, p1.cost * 0.9)), 2)
            if kpi.daily_budget and new_budget > kpi.daily_budget:
                new_budget = round(float(kpi.daily_budget), 2)
            recs.append(
                Recommendation(
                    id=rec_id(stat.source, stat.id, KIND_OVERRUN),
                    source=stat.source,
                    campaign_id=stat.id,
                    campaign_name=stat.name,
                    action_type="budget",
                    title=f"Снизить дневной бюджет «{stat.name}»",
                    reason=(
                        f"За последний день потрачено {fmt_money(p1.cost, currency)} при дневном бюджете "
                        f"{fmt_money(budget, currency)} — превышение на {fmt_money(overrun, currency)}. "
                        f"Рекомендуем поставить {fmt_money(new_budget, currency)} (с запасом 10% на колебания спроса) "
                        f"и разобраться, откуда перерасход (аукцион/корректировки)."
                    ),
                    priority="high",
                    metric_snapshot={"cost_last_day": p1.cost, "budget": budget, "overrun": round(overrun, 2)},
                    changes=[
                        MutationChange(
                            entity="campaign",
                            entity_id=stat.id,
                            entity_name=stat.name,
                            field="daily_budget",
                            before=fmt_money(budget, currency),
                            after=fmt_money(new_budget, currency),
                            payload={
                                "budget_raw_before": budget,
                                "budget_raw_after": new_budget,
                                "budget_resource": f"customers/{stat.id}/campaignBudgets/{stat.id}",
                            },
                        )
                    ],
                    created_at=now_iso(),
                )
            )
        elif p1.cost > 0 and p1.cost < budget * 0.3 and stat.status == "ENABLED":
            warnings.append(
                f"{stat.name}: за последний день израсходовано всего {round(p1.cost / budget * 100)}% бюджета — "
                "проверьте ставки и показы, кампания «недоливает»."
            )

        # --- 2. Низкий CTR ---
        threshold = kpi.target_ctr * (1 - kpi.ctr_deficit_tolerance_pct / 100)
        if p7.impressions >= 100 and p7.ctr < threshold:
            deficit = round((1 - p7.ctr / kpi.target_ctr) * 100) if kpi.target_ctr else 0
            anomalies.append(
                f"{stat.name}: CTR {p7.ctr}% ниже цели {kpi.target_ctr}% (недобор {deficit}%)."
            )
            recs.append(
                Recommendation(
                    id=rec_id(stat.source, stat.id, KIND_CTR_LOW),
                    source=stat.source,
                    campaign_id=stat.id,
                    campaign_name=stat.name,
                    action_type="minus_words",
                    title=f"Добавить минус-слова в «{stat.name}»",
                    reason=(
                        f"CTR за 7 дней {p7.ctr}% при цели {kpi.target_ctr}% — недобор {deficit}%. "
                        "Предлагаем отминусовать нецелевые запросы, чтобы показы не уходили «мимо»; список слов "
                        "собран из поисковых запросов кампании (по расходам без конверсий). После чистки CTR обычно растёт на 10–25%."
                    ),
                    priority="medium" if deficit < 40 else "high",
                    metric_snapshot={"ctr_7d": p7.ctr, "target_ctr": kpi.target_ctr, "clicks_7d": p7.clicks},
                    changes=[],  # заполняется ниже через поисковые запросы
                    created_at=now_iso(),
                )
            )
            rec = recs[-1]
            provider = provider_factory(stat.source)
            if provider is not None:
                try:
                    terms = await _search_terms(provider, item, kpi)
                    if terms:
                        rec.changes = terms
                    else:
                        rec.reason += " Поисковые запросы без явного «мусора» — проверьте заголовки объявлений и "
                        rec.reason += "соответствие текста объявления запросу."
                except AdsApiError as exc:
                    warnings.append(f"{stat.name}: не удалось прочитать поисковые запросы — {exc.message}")

        # --- 3. CPA выше цели ---
        if p7.cpa is not None and kpi.target_cpa > 0:
            allowed = kpi.target_cpa * (1 + kpi.cpa_overrun_tolerance_pct / 100)
            if p7.cpa > allowed and p7.clicks >= kpi.min_clicks_for_judgement:
                excess = round((p7.cpa / kpi.target_cpa - 1) * 100)
                anomalies.append(
                    f"{stat.name}: CPA {fmt_money(p7.cpa, currency)} против цели {fmt_money(kpi.target_cpa, currency)} (+{excess}%)."
                )
                recs.append(
                    Recommendation(
                        id=rec_id(stat.source, stat.id, KIND_CPA_HIGH),
                        source=stat.source,
                        campaign_id=stat.id,
                        campaign_name=stat.name,
                        action_type="bid",
                        title=f"Снизить ставки в «{stat.name}» на {kpi.bid_step_pct:g}%",
                        reason=(
                            f"CPA за 7 дней {fmt_money(p7.cpa, currency)} при цели {fmt_money(kpi.target_cpa, currency)} "
                            f"(+{excess}%), кликов достаточно ({p7.clicks}) для вывода. Снижаем ставки по ключам с расходом "
                            "без конверсий — это уменьшит стоимость клика и CPA, не отключая показы полностью."
                        ),
                        priority="high" if excess > 50 else "medium",
                        metric_snapshot={"cpa_7d": p7.cpa, "target_cpa": kpi.target_cpa, "cost_7d": p7.cost},
                        changes=[],
                        created_at=now_iso(),
                    )
                )
                rec = recs[-1]
                provider = provider_factory(stat.source)
                if provider is not None:
                    try:
                        rec.changes = await _bid_changes(provider, item, kpi)
                    except AdsApiError as exc:
                        warnings.append(f"{stat.name}: нельзя получить ставки для превью — {exc.message}")
                    if not rec.changes:
                        # ставки недоступны — предлагаем снизить бюджет как безопасный аналог
                        new_budget = round(max(kpi.daily_budget * 0.5, (stat.daily_budget or kpi.daily_budget) * 0.8), 2)
                        rec.action_type = "budget"
                        rec.title = f"Снизить дневной бюджет «{stat.name}»"
                        rec.changes = [
                            MutationChange(
                                entity="campaign",
                                entity_id=stat.id,
                                entity_name=stat.name,
                                field="daily_budget",
                                before=fmt_money(stat.daily_budget or kpi.daily_budget, currency),
                                after=fmt_money(new_budget, currency),
                                payload={
                                    "budget_raw_before": stat.daily_budget or kpi.daily_budget,
                                    "budget_raw_after": new_budget,
                                    "budget_resource": f"customers/{stat.id}/campaignBudgets/{stat.id}",
                                },
                            )
                        ]

        # --- 4. Расход есть, конверсий нет ---
        if p7.cost > 0 and p7.conversions == 0 and p7.clicks >= kpi.min_clicks_for_judgement:
            anomalies.append(
                f"{stat.name}: {p7.clicks} кликов и {fmt_money(p7.cost, currency)} расхода без конверсий за 7 дней."
            )
            recs.append(
                Recommendation(
                    id=rec_id(stat.source, stat.id, KIND_NO_CONVERSIONS),
                    source=stat.source,
                    campaign_id=stat.id,
                    campaign_name=stat.name,
                    action_type="minus_words",
                    title=f"Ограничить нецелевой трафик в «{stat.name}»",
                    reason=(
                        f"За 7 дней {p7.clicks} кликов и {fmt_money(p7.cost, currency)} расхода, но ни одной конверсии. "
                        "Сначала проверьте, что на сайте считается целевое действие (скачивание демо), затем отминусуйте "
                        "запросы-«пожиратели» бюджета."
                    ),
                    priority="high",
                    metric_snapshot={"clicks_7d": p7.clicks, "cost_7d": p7.cost},
                    changes=[],
                    created_at=now_iso(),
                )
            )
            rec = recs[-1]
            provider = provider_factory(stat.source)
            if provider is not None:
                try:
                    rec.changes = await _search_terms(provider, item, kpi, only_wasteful=True)
                except AdsApiError as exc:
                    warnings.append(f"{stat.name}: не удалось прочитать поисковые запросы — {exc.message}")

    # одинаковые предложения по одной кампании не дублируем
    seen: set[str] = set()
    unique: List[Recommendation] = []
    for rec in recs:
        key = f"{rec.campaign_id}|{rec.action_type}|{rec.title}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(rec)
    unique.sort(key=lambda r: priority_rank(r.priority))
    return unique


async def _search_terms(provider, item: CampaignStatPeriods, kpi: KpiSettings, only_wasteful: bool = False) -> List[MutationChange]:
    source = item.campaign.source
    if source == "yandex":
        if hasattr(provider, "search_terms"):
            rows = await provider.search_terms(item.campaign.id, 7)
        else:
            return []
    elif source == "google":
        rows = await provider.search_term_report(_days_ago(7), _date_today(), item.campaign.id)
    else:
        return []

    wasteful = []
    for row in rows or []:
        clicks = int(row.get("clicks") or 0)
        conversions = float(row.get("conversions") or 0)
        cost = float(row.get("cost") or 0)
        if only_wasteful:
            if clicks >= 3 and conversions == 0 and cost > 0:
                wasteful.append(row)
        else:
            if cost > 0 and conversions == 0:
                wasteful.append(row)

    wasteful.sort(key=lambda r: float(r.get("cost") or 0), reverse=True)
    if not wasteful:
        return []
    top = wasteful[:10]
    words = [str(r.get("term") or "").strip() for r in top if r.get("term")]
    terms_text = ", ".join(words)
    adgroups: Dict[str, List[str]] = {}
    for row in top:
        adgroups.setdefault(str(row.get("adgroup_id") or ""), []).append(str(row.get("term")))
    changes = []
    for adgroup_id, items in adgroups.items():
        changes.append(
            MutationChange(
                entity="adgroup",
                entity_id=adgroup_id,
                entity_name=f"Группа {adgroup_id}",
                field="minus_words",
                before="—",
                after=", ".join(items),
                payload={"adgroup_id": adgroup_id, "terms_text": terms_text},
            )
        )
    return changes


async def _bid_changes(provider, item: CampaignStatPeriods, kpi: KpiSettings) -> List[MutationChange]:
    if item.campaign.source != "yandex" or not hasattr(provider, "keywords"):
        return []
    keywords = await provider.keywords(item.campaign.id)
    changes: List[MutationChange] = []
    factor = 1 - kpi.bid_step_pct / 100
    for kw in keywords[:200]:
        bid = kw.get("Bid")
        if not bid:
            continue
        before = round(float(bid) / 1_000_000, 2)
        after = max(0.3, round(before * factor, 2))
        if after >= before:
            continue
        changes.append(
            MutationChange(
                entity="keyword",
                entity_id=str(kw.get("Id")),
                entity_name=str(kw.get("Keyword")),
                field="bid",
                before=fmt_money(before, kpi.currency),
                after=fmt_money(after, kpi.currency),
                payload={"keyword_id": kw.get("Id"), "bid_raw_before": before, "bid_raw_after": after},
            )
        )
    return changes


def _date_today():
    from datetime import date

    return date.today()


def _days_ago(n: int):
    from datetime import timedelta

    return _date_today() - timedelta(days=n)
