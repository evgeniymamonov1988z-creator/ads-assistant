from __future__ import annotations

from datetime import date
from typing import List, Optional

from ..models import CampaignStatPeriods, MutationChange


class AdsApiError(Exception):
    """Ошибка провайдера, уже переведённая на понятный русский язык."""

    def __init__(self, message: str, *, code: str = "PROVIDER_ERROR", retry_after: float | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retry_after = retry_after


class Provider:
    name: str = "base"

    async def fetch_stats(self, date_from: date, date_to: date) -> List[CampaignStatPeriods]:
        raise NotImplementedError

    async def apply_changes(self, changes: List[MutationChange]) -> List[MutationChange]:
        raise NotImplementedError

    async def health(self) -> dict:
        raise NotImplementedError
