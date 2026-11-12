from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Source = Literal["yandex", "google"]
ActionType = Literal["bid", "minus_words", "budget"]
Status = Literal["proposed", "confirmed", "failed", "rejected", "stale"]
Priority = Literal["high", "medium", "low"]


class CampaignStat(BaseModel):
    id: str
    name: str
    source: Source
    impressions: int = 0
    clicks: int = 0
    cost: float = 0.0
    conversions: float = 0.0
    ctr: float = 0.0
    cpc: float = 0.0
    cpa: Optional[float] = None
    daily_budget: Optional[float] = None
    status: str = "ENABLED"


class PeriodStats(BaseModel):
    label: str
    date_from: date
    date_to: date
    impressions: int = 0
    clicks: int = 0
    cost: float = 0.0
    conversions: float = 0.0
    ctr: float = 0.0
    cpc: float = 0.0
    cpa: Optional[float] = None
    days: int = 1
    cost_per_day: float = 0.0


class CampaignStatPeriods(BaseModel):
    campaign: CampaignStat
    last7: PeriodStats
    lastDay: PeriodStats


class MutationChange(BaseModel):
    """Одно атомарное изменение (для превью и применения)."""

    entity: str  # campaign / keyword / adgroup
    entity_id: str
    entity_name: str
    field: str  # bid / minus_words / daily_budget
    before: str
    after: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class Recommendation(BaseModel):
    id: str
    source: Source
    campaign_id: str
    campaign_name: str
    action_type: ActionType
    title: str
    reason: str
    priority: Priority
    metric_snapshot: Dict[str, Any] = Field(default_factory=dict)
    changes: List[MutationChange] = Field(default_factory=list)
    created_at: str = ""
    status: Status = "proposed"


class JournalEntry(BaseModel):
    id: str
    created_at: str
    campaign_name: str
    source: Source
    action_type: ActionType
    status: Status
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[str] = None
    title: str = ""
    result: str = ""
    details: str = ""


class KpiSettings(BaseModel):
    target_cpa: float = 300.0
    target_ctr: float = 2.0
    daily_budget: float = 1000.0
    currency: str = "RUB"
    overrun_tolerance_pct: float = 15.0
    ctr_deficit_tolerance_pct: float = 20.0
    cpa_overrun_tolerance_pct: float = 25.0
    min_clicks_for_judgement: int = 30
    bid_step_pct: float = 15.0
    allowed_sources: List[Source] = Field(default_factory=lambda: ["yandex", "google"])


class AnalysisRequest(BaseModel):
    sources: Optional[List[Source]] = None


class AnalysisResponse(BaseModel):
    generated_at: str
    kpi: KpiSettings
    summary: PeriodStats
    by_source: Dict[str, PeriodStats]
    campaigns: List[CampaignStatPeriods]
    recommendations: List[Recommendation]
    anomalies: List[str]
    warnings: List[str] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    confirmed_by: str = Field(min_length=2, max_length=120)


class ConfirmResponse(BaseModel):
    recommendation_id: str
    status: Status
    message: str
    applied: List[MutationChange] = Field(default_factory=list)
    failed: List[Dict[str, str]] = Field(default_factory=list)
