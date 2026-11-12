from __future__ import annotations

from typing import Iterable, List, Optional

from ..models import CampaignStatPeriods, PeriodStats


def enrich(period: PeriodStats) -> PeriodStats:
    """Считает CTR, CPC, CPA, среднесуточный расход на основе «сырых» показов/кликов/расхода."""
    impressions = max(period.impressions, 0)
    clicks = max(period.clicks, 0)
    cost = max(period.cost, 0.0)
    conversions = max(period.conversions, 0.0)
    period.ctr = round(clicks / impressions * 100, 2) if impressions else 0.0
    period.cpc = round(cost / clicks, 2) if clicks else 0.0
    period.cpa = round(cost / conversions, 2) if conversions > 0 else None
    days = max(period.days, 1)
    period.cost_per_day = round(cost / days, 2)
    return period


def sum_periods(periods: Iterable[PeriodStats], label: str) -> PeriodStats:
    items = list(periods)
    if not items:
        today = date_today()
        return enrich(PeriodStats(label=label, date_from=today, date_to=today))
    total = PeriodStats(
        label=label,
        date_from=min(p.date_from for p in items),
        date_to=max(p.date_to for p in items),
        impressions=sum(p.impressions for p in items),
        clicks=sum(p.clicks for p in items),
        cost=round(sum(p.cost for p in items), 2),
        conversions=round(sum(p.conversions for p in items), 2),
        days=max(p.days for p in items),
    )
    return enrich(total)


def date_today():
    from datetime import date

    return date.today()


def overall(campaigns: List[CampaignStatPeriods]) -> tuple[PeriodStats, dict[str, PeriodStats]]:
    p7 = sum_periods((c.last7 for c in campaigns), "7 дней")
    p1 = sum_periods((c.lastDay for c in campaigns), "последний день")
    p7.days = 7
    p1.days = 1
    enrich(p7)
    enrich(p1)
    by_source = {}
    for source in {c.campaign.source for c in campaigns}:
        subset = [c for c in campaigns if c.campaign.source == source]
        by_source[source] = sum_periods((c.last7 for c in subset), source)
        by_source[source].days = 7
        enrich(by_source[source])
    return p7, {**by_source, "last_day": p1}


def fmt_money(value: Optional[float], currency: str = "RUB") -> str:
    if value is None:
        return "—"
    sign = "₽" if currency == "RUB" else currency
    return f"{value:,.2f} {sign}".replace(",", " ")
