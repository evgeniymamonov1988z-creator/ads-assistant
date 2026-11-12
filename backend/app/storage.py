from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List

from .config import settings
from .models import JournalEntry, KpiSettings

_lock = threading.Lock()

DEFAULT_SETTINGS = KpiSettings()


def load_settings() -> KpiSettings:
    try:
        with open(settings.settings_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return KpiSettings(**raw)
    except FileNotFoundError:
        return DEFAULT_SETTINGS.model_copy()
    except Exception:
        return DEFAULT_SETTINGS.model_copy()


def save_settings(kpi: KpiSettings) -> KpiSettings:
    with _lock:
        tmp = settings.settings_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(kpi.model_dump(), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, settings.settings_path)
    return kpi


def append_journal(entry: JournalEntry) -> None:
    with _lock:
        with open(settings.journal_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n")


def _read_raw() -> List[Dict[str, Any]]:
    if not os.path.exists(settings.journal_path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(settings.journal_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def read_journal() -> List[JournalEntry]:
    entries = []
    for row in _read_raw():
        try:
            entries.append(JournalEntry(**row))
        except Exception:
            continue
    entries.sort(key=lambda e: e.created_at, reverse=True)
    return entries


def find_entry(entry_id: str) -> Dict[str, Any] | None:
    for row in _read_raw():
        if row.get("id") == entry_id:
            return row
    return None


def update_entry(entry_id: str, patch: Dict[str, Any]) -> None:
    """Журнал append-only, но статус записи обновляется перезаписью файла (атомарно)."""
    with _lock:
        rows = _read_raw()
        for row in rows:
            if row.get("id") == entry_id:
                row.update(patch)
        tmp = settings.journal_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, settings.journal_path)


def pending_recommendations() -> List[Dict[str, Any]]:
    """Рекомендации, ещё не подтверждённые и не устаревшие — для повторного подтверждения после рестарта."""
    latest: Dict[str, Dict[str, Any]] = {}
    for row in _read_raw():
        latest[row.get("id", "")] = row
    return [r for r in latest.values() if r.get("status") == "proposed"]
