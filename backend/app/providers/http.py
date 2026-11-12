from __future__ import annotations

import asyncio
import email.utils
import time
from typing import Any, Dict, Optional

import httpx

from .base import AdsApiError

# Разбор типовых сетевых проблем -> понятный русский текст
NETWORK_HINTS = [
    ("getaddrinfo", "Не удалось разрешить адрес API. Проверьте интернет или DNS на сервере."),
    ("timeout", "Сервер API не ответил за отведённое время. Повторите запрос позже."),
    ("ssl", "Ошибка защищённого соединения (SSL). Проверьте системное время и сертификаты."),
    ("connect", "Не удалось подключиться к API. Возможно, доступ блокируется сетью (для Google Ads из РФ нужен доступ без ограничений)."),
]


def network_error_text(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    for needle, message in NETWORK_HINTS:
        if needle in text:
            return message
    return "Сетевая ошибка при обращении к API. Попробуйте позже."


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        ts = email.utils.parsedate_to_datetime(value).timestamp()
        return max(0.0, ts - time.time())
    except Exception:
        return None


class LimitedHttp:
    """Небольшая обёртка: таймауты, повторы на 429/5xx и разбор Retry-After."""

    def __init__(self, timeout: int = 30, max_retries: int = 2) -> None:
        self.timeout = timeout
        self.max_retries = max_retries

    async def json(
        self,
        method: str,
        url: str,
        *,
        headers: Dict[str, str] | None = None,
        params: Dict[str, Any] | None = None,
        data: Any = None,
        auth=None,
    ) -> Dict[str, Any]:
        attempt = 0
        last_error: Exception | None = None
        while attempt <= self.max_retries:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    resp = await client.request(
                        method, url, headers=headers, params=params, content=data, auth=auth
                    )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt > self.max_retries:
                    raise AdsApiError(network_error_text(exc), code="NETWORK") from exc
                await asyncio.sleep(1.5 * attempt)
                continue

            if resp.status_code in (429, 500, 502, 503, 504):
                wait = parse_retry_after(resp.headers.get("Retry-After"))
                last_error = AdsApiError(
                    "API временно ограничил запросы (слишком много обращений или технические работы). "
                    "Мы подождали и повторили, но ответа нет — попробуйте позже.",
                    code="RATE_LIMIT",
                    retry_after=wait,
                )
                if attempt > self.max_retries:
                    raise last_error
                await asyncio.sleep(min(wait or 2.0 * attempt, 15.0))
                continue

            try:
                return {"status_code": resp.status_code, **(resp.json() if resp.content else {})}
            except Exception:
                return {"status_code": resp.status_code, "raw_text": resp.text[:500]}
        raise AdsApiError(network_error_text(last_error or Exception("unknown")), code="NETWORK")
