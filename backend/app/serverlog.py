from __future__ import annotations

import os
import re
from collections import Counter, OrderedDict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from .credentials import get_value

# Пример строки nginx/apache:
# 141.8.192.25 - - [12/Nov/2026:10:15:32 +0300] "GET /download/demo.exe HTTP/1.1" 200 152345 "-" "Mozilla/5.0 ..."
LINE_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>[A-Z]+) (?P<path>\S+)[^"]*" (?P<status>\d{3}) (?P<size>\d+|-)'
)
BOT_HINTS = ("bot", "crawler", "spider", "yandexmetrika", "yandexbot", "googlebot", "bingbot", "ahrefs", "semrush", "curl", "wget", "python-requests", "headless")


def _pattern() -> str:
    return (get_value("download_pattern") or "download_demo|/demo/|.exe").strip()


def _path() -> str:
    return (get_value("server_log_path") or "").strip()


def config_status() -> Dict[str, Any]:
    path = _path()
    if not path:
        return {"ok": False, "path": "", "message": "Путь к журналу сервера не указан. Впишите его на вкладке «Токены», если хотите видеть запуски и скачивания из логов."}
    if not os.path.exists(path):
        return {"ok": False, "path": path, "message": "Файл журнала по этому пути не найден. Проверьте путь и права на чтение."}
    if not os.access(path, os.R_OK):
        return {"ok": False, "path": path, "message": "Нет прав на чтение файла журнала. Обратитесь к хостингу, чтобы выдали доступ."}
    return {"ok": True, "path": path, "message": "Журнал найден и читается."}


def _parse_ts(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw.split()[0], "%d/%b/%Y:%H:%M:%S")
    except Exception:
        return None


def _is_bot(agent: str) -> bool:
    low = agent.lower()
    return any(hint in low for hint in BOT_HINTS)


def _tail(path: str, max_bytes: int = 24 * 1024 * 1024) -> List[str]:
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        if size > max_bytes:
            fh.seek(size - max_bytes)
            fh.readline()  # отбрасываем обрезанную строку
        return fh.read().decode("utf-8", errors="ignore").splitlines()


def read_events(days: int = 7, limit: int = 400) -> Dict[str, Any]:
    """Возвращает скачивания и обращения к файлам из журнала сервера."""
    status = config_status()
    if not status["ok"]:
        return {"ok": False, "message": status["message"], "path": status["path"], "events": [], "summary": {}, "by_day": [], "top_files": [], "by_ip": 0}

    try:
        lines = _tail(status["path"])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"Не удалось прочитать журнал: {type(exc).__name__}", "path": status["path"], "events": [], "summary": {}, "by_day": [], "top_files": [], "by_ip": 0}

    try:
        pattern = re.compile(_pattern(), re.IGNORECASE)
    except re.error:
        pattern = re.compile(re.escape(_pattern()), re.IGNORECASE)

    cutoff = datetime.now() - timedelta(days=max(1, min(days, 60)))
    events: List[Dict[str, Any]] = []
    per_day: Counter[str] = Counter()
    per_file: Counter[str] = Counter()
    per_hour: Counter[str] = Counter()
    ips: set[str] = set()
    bad_status = 0

    for line in lines:
        if not pattern.search(line):
            continue
        match = LINE_RE.match(line)
        if not match:
            continue
        path = match.group("path").split("?")[0]
        if not pattern.search(path):
            continue
        agent = line[match.end():] if match else ""
        if _is_bot(agent):
            continue
        ts = _parse_ts(match.group("ts"))
        if ts is None or ts < cutoff:
            continue
        code = int(match.group("status"))
        if code >= 400:
            bad_status += 1
            continue
        size = 0 if match.group("size") == "-" else int(match.group("size"))
        day = ts.date().isoformat()
        per_day[day] += 1
        per_file[path] += 1
        per_hour[f"{ts.hour:02d}"] += 1
        ips.add(match.group("ip"))
        events.append(
            {
                "at": ts.strftime("%d.%m.%Y %H:%M"),
                "date": day,
                "ip": match.group("ip"),
                "file": path,
                "size_kb": round(size / 1024, 1) if size else 0,
                "status": code,
            }
        )

    events.sort(key=lambda e: e["at"], reverse=True)
    day_list = [{"date": d, "count": c} for d, c in sorted(per_day.items())]
    top = [{"file": f, "count": c} for f, c in per_file.most_common(8)]
    hours = [{"hour": h, "count": per_hour.get(f"{i:02d}", 0)} for i, h in ((i, f"{i:02d}") for i in range(24))]
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    return {
        "ok": True,
        "message": "Журнал прочитан.",
        "path": status["path"],
        "events": events[: max(1, min(limit, 2000))],
        "summary": {
            "total": len(events),
            "today": per_day.get(today, 0),
            "yesterday": per_day.get(yesterday, 0),
            "unique_ips": len(ips),
            "errors": bad_status,
            "days": max(1, min(days, 60)),
        },
        "by_day": day_list,
        "by_hour": hours,
        "top_files": top,
        "by_ip": len(ips),
    }
