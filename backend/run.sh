#!/usr/bin/env bash
# Запуск приложения. Секреты берутся из backend/.env или переменных окружения.
set -e
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
exec python3 -m uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
