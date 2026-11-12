from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List

from .config import settings

_lock = threading.Lock()

# Поля, которые можно вписывать из интерфейса (ключ -> как подставить в окружение)
SECRET_FIELDS: List[Dict[str, Any]] = [
    {"source": "yandex", "key": "yd_oauth_token", "env": "YANDEX_OAUTH_TOKEN", "label": "OAuth-токен Яндекс Директа", "secret": True,
     "hint": "Из сервиса регистрации приложений Яндекса. Один токен для чтения статистики и изменения ставок."},
    {"source": "yandex", "key": "yd_agency_client_login", "env": "YANDEX_AGENCY_CLIENT_LOGIN", "label": "Логин клиента (только для агентских аккаунтов)", "secret": False,
     "hint": "Обычно оставьте пустым."},
    {"source": "google", "key": "gads_developer_token", "env": "GOOGLE_ADS_DEVELOPER_TOKEN", "label": "Developer token", "secret": True,
     "hint": "Из Google Ads API Center (инструменты и настройки API)."},
    {"source": "google", "key": "gads_client_id", "env": "GOOGLE_CLIENT_ID", "label": "Client ID (OAuth)", "secret": False,
     "hint": "Из проекта в Google Cloud Console."},
    {"source": "google", "key": "gads_client_secret", "env": "GOOGLE_CLIENT_SECRET", "label": "Client secret (OAuth)", "secret": True,
     "hint": "Рядом с Client ID."},
    {"source": "google", "key": "gads_refresh_token", "env": "GOOGLE_REFRESH_TOKEN", "label": "Refresh token", "secret": True,
     "hint": "Получается один раз при авторизации и живёт долго."},
    {"source": "google", "key": "gads_login_customer_id", "env": "GOOGLE_LOGIN_CUSTOMER_ID", "label": "Управляющий аккаунт (MCC), без дефисов", "secret": False,
     "hint": "Можно оставить пустым, если работаете напрямую."},
    {"source": "metrika", "key": "ym_counter_id", "env": "YM_COUNTER_ID", "label": "Номер счётчика Метрики", "secret": False,
     "hint": "Число из адреса отчёта Метрики (например 112337107). Токен Директа подходит и для Метрики."},
    {"source": "metrika", "key": "ym_goal_download", "env": "YM_GOAL_DOWNLOAD", "label": "Цель «скачивание демо» (имя, можно пустым)", "secret": False,
     "hint": "Если оставить пустым, будут показаны все цели сайта."},
    {"source": "server", "key": "server_log_path", "env": "SERVER_LOG_PATH", "label": "Путь к журналу сервера (access-лог)", "secret": False,
     "hint": "Например /home/a1306338/domains/evgeniymamonov.com/logs/access.log — если журнала нет, оставьте пустым."},
    {"source": "server", "key": "download_pattern", "env": "DOWNLOAD_PATTERN", "label": "Признак «скачали файл» в журнале", "secret": False,
     "hint": "Через вертикальную черту: download_demo|/demo/|.exe"},
    {"source": "google", "key": "gads_customer_id", "env": "GOOGLE_CUSTOMER_ID", "label": "Номер рекламного аккаунта, без дефисов", "secret": False,
     "hint": "Например 1234567890."},
]

SOURCES = ("yandex", "google", "metrika", "server")
_BY_SOURCE = {s: [f for f in SECRET_FIELDS if f["source"] == s] for s in SOURCES}

SOURCE_LABELS = {
    "yandex": "Яндекс Директ",
    "google": "Google Ads",
    "metrika": "Яндекс Метрика (сайт)",
    "server": "Журнал сервера (запуски и скачивания)",
}


def _store_path() -> str:
    return os.path.join(settings.data_dir, "credentials.json")


def _read_store() -> Dict[str, str]:
    try:
        with open(_store_path(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return {k: str(v) for k, v in raw.items() if v}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_store(data: Dict[str, str]) -> None:
    path = _store_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    os.replace(tmp, path)


def get_value(key: str) -> str:
    """Текущее значение поля (сохранённое в интерфейсе или из .env)."""
    return (getattr(settings, key, "") or "").strip()


def _apply(values: Dict[str, str]) -> None:
    """Кладём значения в окружение и в текущий объект настроек движка."""
    env_of = {f["key"]: f["env"] for f in SECRET_FIELDS}
    for key, value in values.items():
        env_name = env_of.get(key)
        if not env_name:
            continue
        value = (value or "").strip()
        if value:
            os.environ[env_name] = value
        else:
            os.environ.pop(env_name, None)
        setattr(settings, key, value)


def load_saved() -> None:
    """Применяем сохранённые из интерфейса значения при старте."""
    saved = _read_store()
    if saved:
        _apply(saved)


def _mask(value: str, field: Dict[str, Any]) -> str:
    if not value:
        return ""
    if not field["secret"]:
        return value
    if len(value) <= 8:
        return "•" * len(value)
    return value[:4] + "•" * 6 + value[-4:]


def _is_ready(source: str) -> bool:
    if source == "yandex":
        return settings.yandex_configured
    if source == "google":
        return settings.google_configured
    if source == "metrika":
        return settings.metrika_configured
    return bool(settings.server_log_path)


def public_view() -> Dict[str, Any]:
    sources = []
    for source, fields in _BY_SOURCE.items():
        rows = []
        for f in fields:
            value = getattr(settings, f["key"], "") or ""
            rows.append(
                {
                    "key": f["key"],
                    "env": f["env"],
                    "label": f["label"],
                    "hint": f["hint"],
                    "secret": f["secret"],
                    "filled": bool(value),
                    "preview": _mask(value, f),
                }
            )
        sources.append(
            {
                "source": source,
                "label": SOURCE_LABELS.get(source, source),
                "ready": _is_ready(source),
                "fields": rows,
            }
        )
    return {
        "sources": sources,
        "mock_mode": settings.mock_mode,
        "storage_note": "Значения хранятся только на этом компьютере, в служебной папке приложения, и в интерфейсе показываются в виде подсказки (первые и последние символы).",
    }


def save_source(source: str, payload: Dict[str, str], clear: List[str] | None = None) -> Dict[str, Any]:
    if source not in _BY_SOURCE:
        raise ValueError("Неизвестный источник")
    allowed = {f["key"] for f in _BY_SOURCE[source]}
    updates: Dict[str, str] = {}
    for key, value in (payload or {}).items():
        if key in allowed and isinstance(value, str):
            # Пустое поле = «не менять». Очистка — только через clear.
            if value.strip():
                updates[key] = value.strip()
    for key in clear or []:
        if key in allowed:
            updates[key] = ""

    if inputs_look_wrong(updates):
        raise ValueError(
            "Похоже, в поле вставлен не токен, а текст запроса (например «Привет!»). "
            "Вставьте значение, скопированное из кабинета соответствующего сервиса."
        )

    with _lock:
        store = _read_store()
        for key, value in updates.items():
            if value:
                store[key] = value
            else:
                store.pop(key, None)
        _write_store(store)
        _apply(updates)
    return public_view()


def inputs_look_wrong(values: Dict[str, str]) -> bool:
    """Грубая защита: длинные пробельные фразы вместо токена."""
    for key, value in values.items():
        if not value:
            continue
        field = next((f for f in SECRET_FIELDS if f["key"] == key), None)
        if field and field["secret"]:
            if any(ch.isspace() for ch in value) and len(value.split()) >= 3:
                return True
            if len(value) < 8:
                return True
    return False
