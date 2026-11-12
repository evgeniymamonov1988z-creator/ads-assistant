from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import settings
from .credentials import load_saved as load_saved_credentials

load_saved_credentials()

app = FastAPI(
    title=settings.app_name,
    description="Ассистент рекламы: Яндекс Директ API v5 + Google Ads API. Анализ, предложения, подтверждение.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    """Простая защита от чужих запросов: если задан API_KEY, мутации требуют его в заголовке."""
    expected = os.environ.get("API_KEY", "").strip()
    if expected and request.url.path.startswith("/api") and request.method in ("POST", "PUT"):
        provided = request.headers.get("x-api-key", "")
        if provided != expected:
            return JSONResponse(status_code=401, content={"detail": "Нужен ключ доступа: заголовок X-API-Key."})
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера. Попробуйте ещё раз; если повторяется — посмотрите логи."},
    )


app.include_router(router)


@app.get("/api/config")
def public_config() -> Dict[str, Any]:
    return {
        "app": settings.app_name,
        "currency": settings.currency,
        "mock_mode": settings.mock_mode,
        "sources": settings.sources_status(),
    }


# --- Раздача собранного React-приложения ---
DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
if os.path.isdir(os.path.join(DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Не найдено"})
    index = os.path.join(DIST, "index.html")
    candidate = os.path.join(DIST, full_path)
    if full_path and os.path.isfile(candidate):
        return FileResponse(candidate)
    if os.path.isfile(index):
        return FileResponse(index)
    return JSONResponse(
        status_code=200,
        content={
            "message": "Сервер работает. Фронтенд не собран: выполните `npm run build` во frontend, "
            "либо откройте в режиме разработки http://localhost:5173",
        },
    )
