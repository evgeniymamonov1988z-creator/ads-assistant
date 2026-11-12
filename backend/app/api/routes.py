from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..credentials import public_view as credentials_view, save_source as save_credentials
from ..core.engine import describe_changes, label, make_provider, run_analysis
from ..models import (
    AnalysisRequest,
    AnalysisResponse,
    ConfirmRequest,
    ConfirmResponse,
    JournalEntry,
    KpiSettings,
    MutationChange,
    Recommendation,
)
from ..providers.base import AdsApiError
from ..storage import append_journal, load_settings, read_journal, save_settings, update_entry
from ..core.rules import now_iso, priority_rank

router = APIRouter(prefix="/api")

# --- Кэш предложений: подтвердить можно только то, что реально было показано пользователю ---
PENDING: Dict[str, Recommendation] = {}
PENDING_LOCK = asyncio.Lock()


@router.get("/health")
async def health() -> Dict[str, Any]:
    sources = []
    for source in ("yandex", "google"):
        provider = make_provider(source)
        if provider is None:
            continue
        try:
            sources.append(await asyncio.wait_for(provider.health(), timeout=settings.request_timeout + 5))
        except asyncio.TimeoutError:
            sources.append({"source": source, "ok": False, "message": "Проверка подключения заняла слишком много времени."})
        except Exception as exc:  # noqa: BLE001
            sources.append({"source": source, "ok": False, "message": f"Ошибка проверки: {type(exc).__name__}"})
    return {"app": settings.app_name, "mock_mode": settings.mock_mode, "sources": sources}


@router.get("/settings", response_model=KpiSettings)
def get_settings() -> KpiSettings:
    return load_settings()


@router.put("/settings", response_model=KpiSettings)
def put_settings(kpi: KpiSettings) -> KpiSettings:
    if kpi.target_cpa < 0 or kpi.target_ctr < 0 or kpi.daily_budget < 0:
        raise HTTPException(status_code=400, detail="Целевые значения не могут быть отрицательными.")
    if kpi.target_ctr > 100:
        raise HTTPException(status_code=400, detail="Целевой CTR не может быть больше 100%.")
    save_settings(kpi)
    return kpi


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(req: AnalysisRequest | None = None) -> AnalysisResponse:
    kpi = load_settings()
    result = await run_analysis(kpi, req)
    async with PENDING_LOCK:
        PENDING.clear()
        for rec in result.recommendations:
            if rec.changes:
                PENDING[rec.id] = rec
    return result


@router.get("/journal", response_model=List[JournalEntry])
def journal(limit: int = 200) -> List[JournalEntry]:
    return read_journal()[: max(1, min(limit, 1000))]


@router.get("/journal.csv")
def journal_csv():
    from fastapi.responses import Response

    rows = read_journal()
    header = ["дата", "кампания", "источник", "тип действия", "статус", "кто подтвердил", "что сделано", "результат"]
    lines = [";".join(header)]
    for row in rows:
        lines.append(
            ";".join(
                csv_cell(value)
                for value in [
                    row.created_at,
                    row.campaign_name,
                    label(row.source),
                    row.action_type,
                    status_ru(row.status),
                    row.confirmed_by or "",
                    row.title,
                    row.result,
                ]
            )
        )
    csv = "\ufeff" + "\n".join(lines)
    return Response(
        content=csv.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="adassistant-journal.csv"'},
    )


@router.post("/recommendations/{rec_id}/confirm", response_model=ConfirmResponse)
async def confirm(rec_id: str, body: ConfirmRequest) -> ConfirmResponse:
    async with PENDING_LOCK:
        rec = PENDING.get(rec_id)
    if rec is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Это предложение больше не актуально (сервер перезапускался или данные обновились). "
                "Запустите анализ заново и подтвердите свежую рекомендацию."
            ),
        )
    if not rec.changes:
        raise HTTPException(status_code=400, detail="В рекомендации нет изменений для применения.")

    provider = make_provider(rec.source)
    if provider is None:
        raise HTTPException(status_code=400, detail="Источник рекламы не поддерживается.")

    confirmed_by = body.confirmed_by.strip()
    base_entry = find_entry(rec.id)
    confirmed_at = now_iso()

    try:
        applied = await asyncio.wait_for(provider.apply_changes(rec.changes), timeout=settings.request_timeout + 15)
    except asyncio.TimeoutError:
        message = "API не ответил вовремя. Изменения могли не примениться — проверьте кампанию вручную перед повтором."
        mark(rec.id, "failed", confirmed_by, confirmed_at, message)
        raise HTTPException(status_code=504, detail=message) from None
    except AdsApiError as exc:
        message = exc.message
        if exc.code == "RATE_LIMIT":
            message += " Рекомендация осталась в ожидании — повторите подтверждение позже."
            update_result(rec.id, f"Не применено: {message}")
            raise HTTPException(status_code=429, detail=message) from None
        mark(rec.id, "failed", confirmed_by, confirmed_at, message)
        raise HTTPException(status_code=502, detail=message) from None
    except Exception as exc:  # noqa: BLE001
        message = f"Непредвиденная ошибка при отправке изменений ({type(exc).__name__}). Изменения не подтверждены."
        mark(rec.id, "failed", confirmed_by, confirmed_at, message)
        raise HTTPException(status_code=502, detail=message) from None

    async with PENDING_LOCK:
        PENDING.pop(rec.id, None)

    mark(
        rec.id,
        "confirmed",
        confirmed_by,
        confirmed_at,
        f"Применено изменений: {len(applied)}",
        details=describe_changes(applied),
    )
    return ConfirmResponse(
        recommendation_id=rec.id,
        status="confirmed",
        message=f"Готово: применено изменений — {len(applied)}.",
        applied=applied,
    )


@router.post("/recommendations/{rec_id}/reject", response_model=ConfirmResponse)
async def reject(rec_id: str, body: ConfirmRequest) -> ConfirmResponse:
    async with PENDING_LOCK:
        rec = PENDING.pop(rec_id, None)
    if rec is None:
        raise HTTPException(status_code=409, detail="Предложение уже неактуально.")
    mark(rec_id, "rejected", body.confirmed_by.strip(), now_iso(), "Отклонено пользователем", details="Изменения не отправлялись")
    return ConfirmResponse(recommendation_id=rec_id, status="rejected", message="Предложение отклонено, в API ничего не отправлялось.")


def find_entry(entry_id: str) -> Dict[str, Any] | None:
    from ..storage import find_entry as _find

    return _find(entry_id)


def mark(entry_id: str, status: str, by: str, at: str, result: str, details: str | None = None) -> None:
    patch: Dict[str, Any] = {
        "status": status,
        "confirmed_by": by,
        "confirmed_at": at,
        "result": result,
    }
    if details:
        patch["details"] = details
    if find_entry(entry_id) is None:
        # запись могла не сохраниться (рестарт) — создаём её, чтобы журнал не терялся
        append_journal(
            JournalEntry(
                id=entry_id,
                created_at=at,
                campaign_name="—",
                source="yandex",
                action_type="bid",
                status=status,  # type: ignore[arg-type]
                confirmed_by=by,
                confirmed_at=at,
                result=result,
                details=details or "",
            )
        )
        return
    update_entry(entry_id, patch)


def update_result(entry_id: str, result: str) -> None:
    if find_entry(entry_id) is not None:
        update_entry(entry_id, {"result": result})


def status_ru(status: str) -> str:
    return {
        "proposed": "предложено",
        "confirmed": "подтверждено",
        "failed": "ошибка",
        "rejected": "отклонено",
        "stale": "устарело",
    }.get(status, status)


def csv_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ")
    if ";" in text or '"' in text:
        return '"' + text.replace('"', '""') + '"'
    return text


# --- Яндекс Метрика и журнал сервера (вкладка «Метрика и запуски») ---
@router.get("/metrika")
async def metrika(days: int = 7) -> Dict[str, Any]:
    from ..providers.metrika import MetrikaProvider

    return await MetrikaProvider().snapshot(days=max(1, min(days, 60)))


@router.get("/serverlog")
def serverlog(days: int = 7, limit: int = 400) -> Dict[str, Any]:
    from ..serverlog import read_events

    return read_events(days=max(1, min(days, 60)), limit=limit)


@router.get("/serverlog.csv")
def serverlog_csv(days: int = 7):
    from fastapi.responses import Response

    from ..serverlog import read_events

    data = read_events(days=max(1, min(days, 60)), limit=2000)
    header = ["дата и время", "файл", "IP", "размер, КБ", "код ответа"]
    lines = [";".join(header)]
    for row in data.get("events", []):
        lines.append(
            ";".join(
                csv_cell(value)
                for value in [row["at"], row["file"], row["ip"], str(row["size_kb"]), str(row["status"])]
            )
        )
    csv = "\ufeff" + "\n".join(lines)
    return Response(
        content=csv.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="adassistant-downloads.csv"'},
    )


# --- Токены и доступы (вкладка «Токены») ---
@router.get("/credentials")
def get_credentials() -> Dict[str, Any]:
    return credentials_view()


@router.put("/credentials/{source}")
def put_credentials(source: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    values = payload.get("values") or {}
    clear = payload.get("clear") or []
    if not isinstance(values, dict) or not isinstance(clear, list):
        raise HTTPException(status_code=400, detail="Неверный формат данных.")
    clean = {str(k): v for k, v in values.items() if isinstance(v, str)}
    try:
        view = save_credentials(source, clean, [str(c) for c in clear])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return view


@router.post("/credentials/test")
async def test_credentials() -> Dict[str, Any]:
    """Пробное обращение к API с текущими значениями (без изменений в кабинетах)."""
    results = []
    for source in ("yandex", "google", "metrika", "server"):
        if source == "server":
            from ..serverlog import config_status

            status = config_status()
            results.append({"source": "server", "ok": status["ok"], "message": status["message"]})
            continue
        if source == "metrika":
            from ..providers.metrika import MetrikaProvider

            if settings.mock_mode:
                results.append({"source": "metrika", "ok": False, "message": "Включён демо-режим: проверка не выполняется."})
            else:
                results.append(await MetrikaProvider().health())
            continue
        provider = None
        if not settings.mock_mode:
            from ..core.engine import make_provider  # локальный импорт, чтобы подхватить новые значения

            provider = make_provider(source)
        if provider is None:
            results.append({"source": source, "ok": False, "message": "Включён демо-режим: проверка не выполняется."})
            continue
        try:
            results.append(await asyncio.wait_for(provider.health(), timeout=settings.request_timeout + 5))
        except asyncio.TimeoutError:
            results.append({"source": source, "ok": False, "message": "Сервис не ответил вовремя. Проверьте интернет и повторите."})
        except Exception as exc:  # noqa: BLE001
            results.append({"source": source, "ok": False, "message": f"Ошибка проверки: {type(exc).__name__}"})
    return {"sources": results}
