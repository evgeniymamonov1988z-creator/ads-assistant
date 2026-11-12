from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass
class Settings:
    """Всё секретное берётся ТОЛЬКО из переменных окружения (.env)."""

    app_name: str = "Рекламный ассистент"
    data_dir: str = _env("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data"))
    app_secret: str = _env("APP_SECRET", "change-me")

    # --- Yandex Direct API v5 ---
    yd_client_id: str = _env("YANDEX_CLIENT_ID")
    yd_client_secret: str = _env("YANDEX_CLIENT_SECRET")
    yd_oauth_token: str = _env("YANDEX_OAUTH_TOKEN")
    yd_refresh_token: str = _env("YANDEX_REFRESH_TOKEN")
    yd_agency_client_login: str = _env("YANDEX_AGENCY_CLIENT_LOGIN")
    yd_api_url: str = _env("YANDEX_API_URL", "https://api.direct.yandex.com/json/v5")
    yd_api_lang: str = _env("YANDEX_API_LANG", "ru")

    # --- Google Ads API ---
    gads_developer_token: str = _env("GOOGLE_ADS_DEVELOPER_TOKEN")
    gads_client_id: str = _env("GOOGLE_CLIENT_ID")
    gads_client_secret: str = _env("GOOGLE_CLIENT_SECRET")
    gads_refresh_token: str = _env("GOOGLE_REFRESH_TOKEN")
    gads_login_customer_id: str = _env("GOOGLE_LOGIN_CUSTOMER_ID")
    gads_customer_id: str = _env("GOOGLE_CUSTOMER_ID")
    gads_api_version: str = _env("GOOGLE_ADS_API_VERSION", "v19")

    # --- Яндекс Метрика (сайт) ---
    ym_counter_id: str = _env("YM_COUNTER_ID")
    ym_goal_download: str = _env("YM_GOAL_DOWNLOAD")  # имя цели «скачивание демо»

    # --- Журнал сервера (запуски программы и скачивания) ---
    server_log_path: str = _env("SERVER_LOG_PATH")  # путь к access-логу сайта
    download_pattern: str = _env("DOWNLOAD_PATTERN", "download_demo|/demo/|.exe")

    # --- Поведение ---
    mock_mode: bool = _env("MOCK_MODE", "0") in ("1", "true", "True", "yes")
    currency: str = _env("CURRENCY", "RUB")
    request_timeout: int = _env_int("REQUEST_TIMEOUT", 30)
    journal_path: str = ""
    settings_path: str = ""

    def __post_init__(self) -> None:
        self.data_dir = os.path.abspath(self.data_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        self.journal_path = os.path.join(self.data_dir, "journal.jsonl")
        self.settings_path = os.path.join(self.data_dir, "settings.json")

    @property
    def yandex_configured(self) -> bool:
        return bool(self.yd_oauth_token or self.yd_refresh_token)

    @property
    def metrika_configured(self) -> bool:
        return bool((self.yd_oauth_token or self.yd_refresh_token) and self.ym_counter_id)

    @property
    def google_configured(self) -> bool:
        return bool(self.gads_developer_token and (self.gads_refresh_token or self.gads_client_secret))

    def sources_status(self) -> Dict[str, dict]:
        return {
            "yandex": {
                "configured": self.yandex_configured,
                "label": "Яндекс Директ API v5",
                "missing": [] if self.yandex_configured else ["YANDEX_OAUTH_TOKEN / YANDEX_REFRESH_TOKEN"],
            },
            "google": {
                "configured": self.google_configured,
                "label": "Google Ads API",
                "missing": [] if self.google_configured else ["GOOGLE_ADS_DEVELOPER_TOKEN + GOOGLE_REFRESH_TOKEN"],
            },
            "metrika": {
                "configured": self.metrika_configured,
                "label": "Яндекс Метрика",
                "missing": [] if self.metrika_configured else ["YANDEX_OAUTH_TOKEN + YM_COUNTER_ID"],
            },
            "mock_mode": self.mock_mode,
        }


settings = Settings()
