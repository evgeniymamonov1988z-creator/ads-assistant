from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any, Dict, List

from ..models import CampaignStat, CampaignStatPeriods, MutationChange, PeriodStats
from .base import Provider

# Демо-данные, чтобы интерфейс можно было проверить без реальных API-ключей.
DEMO_CAMPAIGNS = [
    ("yandex", "101", "Экранник — Поиск (RU)", 1200.0, 3.4, 260.0),
    ("yandex", "102", "Кадрик — Поиск (RU)", 800.0, 1.1, 480.0),
    ("yandex", "103", "Диктик / VoiceNote — Поиск", 600.0, 2.1, 0.0),
    ("google", "201", "ScreenRecorder — Search EN", 250.0, 2.6, 320.0),
    ("google", "202", "Kadrik — Search EN", 240.0, 0.9, 700.0),
]


class MockProvider(Provider):
    name = "mock"

    async def fetch_stats(self, date_from: date, date_to: date) -> List[CampaignStatPeriods]:
        rnd = random.Random(42)
        out: List[CampaignStatPeriods] = []
        for source, cid, name, budget, ctr, cpa in DEMO_CAMPAIGNS:
            days = (date_to - date_from).days + 1
            clicks7 = rnd.randint(120, 420)
            conv7 = round(clicks7 / max(1.0, cpa / 4.0), 1) if cpa else 0.0
            cost7 = round(clicks7 * (cpa / 4.0 if cpa else 18.0), 2)
            cpc = round(cost7 / clicks7, 2)
            impressions7 = int(clicks7 / (ctr / 100) / max(1, days) * days)
            day_clicks = max(1, clicks7 // (days or 7))
            day_cost = round(day_clicks * cpc * (1.6 if cid == "102" else 1.0), 2)
            day_conv = 0.0 if cid in ("102", "202", "103") else 1.0
            out.append(
                CampaignStatPeriods(
                    campaign=CampaignStat(
                        id=f"{source}-{cid}",
                        name=name,
                        source=source,  # type: ignore[arg-type]
                        impressions=impressions7,
                        clicks=clicks7,
                        cost=cost7,
                        conversions=conv7,
                        cpc=cpc,
                        daily_budget=budget,
                        status="ENABLED",
                    ),
                    last7=PeriodStats(
                        label="7 дн.",
                        date_from=date_from,
                        date_to=date_to,
                        impressions=impressions7,
                        clicks=clicks7,
                        cost=cost7,
                        conversions=conv7,
                        days=days,
                    ),
                    lastDay=PeriodStats(
                        label="1 дн.",
                        date_from=date_to,
                        date_to=date_to,
                        impressions=max(1, impressions7 // 7),
                        clicks=day_clicks,
                        cost=day_cost,
                        conversions=day_conv,
                        days=1,
                    ),
                )
            )
        return out

    async def keywords(self, campaign_id: str) -> List[Dict[str, Any]]:
        rnd = random.Random(f"kw-{campaign_id}")
        bases = ["скачать программу", "запись экрана windows", "извлечь кадр из видео", "распознавание речи офлайн", "screen recorder free"]
        out = []
        for i, base in enumerate(bases):
            out.append({"Id": 9000 + i, "Keyword": base, "Bid": int(rnd.randint(1500, 9000) * 1_000_000)})
        return out

    async def search_terms(self, campaign_id: str, days: int = 7) -> List[Dict[str, Any]]:
        return self._demo_terms(campaign_id)

    async def search_term_report(self, date_from, date_to, campaign_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        return self._demo_terms(campaign_id)

    def _demo_terms(self, campaign_id: str) -> List[Dict[str, Any]]:
        rnd = random.Random(f"st-{campaign_id}")
        terms = [
            ("бесплатно скачать без регистрации", 14, 780.0),
            ("торрент crack", 9, 520.0),
            ("как записать экран на телефоне", 7, 310.0),
            ("программа для записи экрана windows 10", 5, 180.0),
        ]
        return [
            {
                "term": term,
                "adgroup_id": f"ag-{campaign_id}",
                "clicks": clicks,
                "impressions": clicks * rnd.randint(6, 20),
                "cost": cost,
                "conversions": 0.0 if "torrent" in term or "бесплатно" in term else 0.0,
            }
            for term, clicks, cost in terms
        ]

    async def apply_changes(self, changes: List[MutationChange]) -> List[MutationChange]:
        return changes

    async def health(self) -> dict:
        return {"source": "mock", "ok": True, "message": "Демо-режим: реальные API не вызываются"}
