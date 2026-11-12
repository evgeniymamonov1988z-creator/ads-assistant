from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, Dict, List

from ..config import settings
from ..credentials import get_value
from .http import LimitedHttp, network_error_text

METRIKA_URL = "https://api-metrika.yandex.net/stat/v1/data"

METRIKA_ERRORS = {
    403: "Метрика отклонила доступ: проверьте, что токен выдан с правом на чтение статистики и у аккаунта есть доступ к этому счётчику.",
    404: "Счётчик не найден. Проверьте номер счётчика в настройках.",
    429: "Метрика ограничила число обращений подряд. Подождите минуту и повторите.",
}


def _fmt_day(value: date) -> str:
    return value.isoformat()


class MetrikaProvider:
    name = "metrika"

    def __init__(self) -> None:
        self.http = LimitedHttp(timeout=settings.request_timeout)
        self.token = get_value("yd_oauth_token") or settings.yd_oauth_token
        self.counter = get_value("ym_counter_id") or settings.ym_counter_id
        self.goal_site = get_value("ym_goal_download") or settings.ym_goal_download

    def _check(self) -> None:
        if not self.token:
            raise RuntimeError("Яндекс Метрика не настроена: нужен токен Директа (он же подходит для Метрики).")
        if not self.counter:
            raise RuntimeError("Не указан номер счётчика Метрики. Впишите его на вкладке «Токены».")

    async def _query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._check()
        try:
            raw = await self.http.json(
                "GET",
                f"{METRIKA_URL}/{self.counter}",
                headers={"Authorization": f"OAuth {self.token}"},
                params=params,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(network_error_text(exc)) from exc
        status = int(raw.get("status_code", 200))
        if status >= 400:
            message = METRIKA_ERRORS.get(status)
            if not message:
                detail = raw.get("errors") or raw.get("message") or raw.get("raw_text")
                message = f"Метрика вернула ошибку {status}. {detail if isinstance(detail, str) else ''}".strip()
            raise RuntimeError(message)
        return raw

    async def totals(self, date_from: date, date_to: date) -> Dict[str, Any]:
        params = {
            "ids": self.counter,
            "date1": _fmt_day(date_from),
            "date2": _fmt_day(date_to),
            "metrics": "ym:s:visits,ym:s:users,ym:s:pageviews,ym:s:bounceRate,ym:s:avgVisitDurationSeconds",
            "accuracy": "full",
        }
        raw = await self._query(params)
        totals = (raw.get("totals") or [0, 0, 0, 0, 0])
        return {
            "visits": int(totals[0] or 0),
            "users": int(totals[1] or 0),
            "pageviews": int(totals[2] or 0),
            "bounce_rate": round(float(totals[3] or 0), 1),
            "avg_duration": int(totals[4] or 0),
        }

    async def by_day(self, date_from: date, date_to: date) -> List[Dict[str, Any]]:
        raw = await self._query(
            {
                "ids": self.counter,
                "date1": _fmt_day(date_from),
                "date2": _fmt_day(date_to),
                "metrics": "ym:s:visits,ym:s:users",
                "dimensions": "ym:s:date",
                "sort": "ym:s:date",
                "accuracy": "full",
            }
        )
        rows = []
        for item in raw.get("data") or []:
            dim = (item.get("dimensions") or [{}])[0]
            metrics = item.get("metrics") or [0, 0]
            rows.append(
                {
                    "date": (dim.get("name") or "")[:10],
                    "visits": int(metrics[0] or 0),
                    "users": int(metrics[1] or 0),
                }
            )
        return rows

    async def goals(self, date_from: date, date_to: date) -> List[Dict[str, Any]]:
        """Достижения целей — в том числе скачивания демо, если цель заведена."""
        params: Dict[str, Any] = {
            "ids": self.counter,
            "date1": _fmt_day(date_from),
            "date2": _fmt_day(date_to),
            "metrics": "ym:s:goalReaches",
            "dimensions": "ym:s:goal",
            "accuracy": "full",
        }
        if self.goal_site:
            params["filters"] = f"ym:s:goalName=='{self.goal_site}'"
        raw = await self._query(params)
        rows = []
        for item in raw.get("data") or []:
            dim = (item.get("dimensions") or [{}])[0]
            metrics = item.get("metrics") or [0]
            rows.append(
                {
                    "goal_id": str(dim.get("id") or ""),
                    "name": dim.get("name") or "Цель",
                    "reaches": int(metrics[0] or 0),
                    "is_download": (dim.get("name") or "").lower().find("скач") >= 0
                    or (dim.get("name") or "").lower().find("download") >= 0,
                }
            )
        rows.sort(key=lambda r: r["reaches"], reverse=True)
        return rows

    async def sources(self, date_from: date, date_to: date, limit: int = 6) -> List[Dict[str, Any]]:
        raw = await self._query(
            {
                "ids": self.counter,
                "date1": _fmt_day(date_from),
                "date2": _fmt_day(date_to),
                "metrics": "ym:s:visits",
                "dimensions": "ym:s:lastsignTrafficSource",
                "sort": "-ym:s:visits",
                "limit": limit,
                "accuracy": "full",
            }
        )
        names = {
            "organic": "Поиск",
            "ad": "Реклама",
            "direct": "Прямые заходы",
            "internal": "Внутренние",
            "social": "Соцсети",
            "recommend": "Рекомендации",
            "saved": "Сохранённые",
            "messenger": "Мессенджеры",
            "email": "Почта",
            "reference": "Ссылки",
            "undefined": "Не определено",
        }
        rows = []
        for item in raw.get("data") or []:
            dim = (item.get("dimensions") or [{}])[0]
            key = dim.get("id") or dim.get("name") or ""
            metrics = item.get("metrics") or [0]
            rows.append({"source": names.get(key, key or "Другое"), "visits": int(metrics[0] or 0)})
        return rows

    async def snapshot(self, days: int = 7) -> Dict[str, Any]:
        today = date.today()
        date_to = today - timedelta(days=1)
        date_from = date_to - timedelta(days=max(1, days) - 1)
        result: Dict[str, Any] = {
            "ok": False,
            "counter": self.counter,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "message": "",
        }
        try:
            total, days_rows, goals, sources = await asyncio.gather(
                self.totals(date_from, date_to),
                self.by_day(date_from, date_to),
                self.goals(date_from, date_to),
                self.sources(date_from, date_to),
            )
        except RuntimeError as exc:
            result["message"] = str(exc)
            return result
        result.update(total)
        result.update(
            {
                "ok": True,
                "by_day": days_rows,
                "goals": goals,
                "sources": sources,
                "downloads": sum(g["reaches"] for g in goals if g["is_download"]),
            }
        )
        return result

    async def health(self) -> Dict[str, Any]:
        try:
            await self.totals(date.today() - timedelta(days=1), date.today() - timedelta(days=1))
        except RuntimeError as exc:
            return {"source": "metrika", "ok": False, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"source": "metrika", "ok": False, "message": f"Ошибка проверки: {type(exc).__name__}"}
        return {"source": "metrika", "ok": True, "message": "Счётчик доступен, статистика читается."}
