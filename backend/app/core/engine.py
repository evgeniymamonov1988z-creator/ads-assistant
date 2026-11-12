from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List

from ..config import settings
from ..models import (
    AnalysisRequest,
    AnalysisResponse,
    CampaignStatPeriods,
    JournalEntry,
    KpiSettings,
)
from ..providers.base import AdsApiError, Provider
from ..providers.google import GoogleAdsProvider
from ..providers.mock import MockProvider
from ..providers.yandex import YandexProvider
from ..storage import append_journal
from .metrics import enrich, overall
from .rules import build_recommendations, now_iso


def make_provider(source: str) -> Provider | None:
    if settings.mock_mode:
        return MockProvider()
    if source == "yandex":
        return YandexProvider()
    if source == "google":
        return GoogleAdsProvider()
    return None


async def collect_all(date_from: date, date_to: date) -> tuple[List[CampaignStatPeriods], List[str]]:
    campaigns: List[CampaignStatPeriods] = []
    warnings: List[str] = []
    for source in ("yandex", "google"):
        provider = make_provider(source)
        if provider is None:
            continue
        try:
            campaigns.extend(await provider.fetch_stats(date_from, date_to))
        except AdsApiError as exc:
            warnings.append(f"{label(source)}: {exc.message}")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{label(source)}: непредвиденная ошибка ({type(exc).__name__}).")
    return campaigns, warnings


def label(source: str) -> str:
    return {"yandex": "Яндекс Директ", "google": "Google Ads"}.get(source, source)


async def run_analysis(kpi: KpiSettings, req: AnalysisRequest | None = None) -> AnalysisResponse:
    today = date.today()
    date_to = today - timedelta(days=1)  # последний полный день
    date_from = date_to - timedelta(days=6)

    campaigns, warnings = await collect_all(date_from, date_to)
    if not campaigns:
        warnings.append(
            "Нет данных по кампаниям. Проверьте, что источники настроены в переменных окружения "
            "(или включите демо-режим MOCK_MODE=1), и что в кампаниях были показы за период."
        )

    for item in campaigns:
        item.last7 = enrich(item.last7.model_copy())
        item.lastDay = enrich(item.lastDay.model_copy())
        item.campaign.ctr = item.last7.ctr
        item.campaign.cpc = item.last7.cpc
        item.campaign.cpa = item.last7.cpa

    summary, by_source = overall(campaigns)
    anomalies: List[str] = []
    recs = await build_recommendations(
        campaigns, kpi, make_provider, anomalies=anomalies, warnings=warnings
    )

    # каждое предложение фиксируется в журнале со статусом "предложено"
    for rec in recs:
        if not rec.changes:
            continue
        append_journal(
            JournalEntry(
                id=rec.id,
                created_at=rec.created_at or now_iso(),
                campaign_name=rec.campaign_name,
                source=rec.source,
                action_type=rec.action_type,
                status="proposed",
                title=rec.title,
                details=describe_changes(rec.changes),
                result="Ожидает подтверждения",
            )
        )

    anomalies = list(dict.fromkeys(anomalies))

    return AnalysisResponse(
        generated_at=now_iso(),
        kpi=kpi,
        summary=summary,
        by_source=by_source,
        campaigns=campaigns,
        recommendations=recs,
        anomalies=anomalies,
        warnings=warnings,
    )


def describe_changes(changes) -> str:
    parts: List[str] = []
    for index, change in enumerate(changes[:5], start=1):
        field = {"bid": "ставка", "daily_budget": "дневной бюджет", "minus_words": "минус-слова"}.get(
            change.field, change.field
        )
        parts.append(f"{index}) {field}: {change.entity_name} — {change.before} → {change.after}")
    if len(changes) > 5:
        parts.append(f"… и ещё {len(changes) - 5}")
    return "; ".join(parts)
