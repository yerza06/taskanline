#!/usr/bin/env bash
# Бэкенд для Playwright: своя база, свой порт, лимиты на регистрацию сняты
# (сценарии заводят несколько людей с одного адреса), письма — в лог, откуда
# тест достаёт ссылку приглашения.
set -euo pipefail
cd "$(dirname "$0")/../.."

export DB__NAME=taskanline_e2e
export SERVER__HOST=127.0.0.1 SERVER__PORT=8001 SERVER__RELOAD=false
export AUTH__COOKIE_SECURE=false AUTH__REGISTER_ATTEMPTS=1000 AUTH__LOGIN_ATTEMPTS=1000
export APP__ENVIRONMENT=ci APP__PUBLIC_URL=http://localhost:5174
export CORS__ORIGINS=http://localhost:5174 MAILER__BACKEND=console LOG__LEVEL=INFO

uv run python frontend_client/e2e/reset_db.py reset
uv run alembic -c backend/alembic.ini upgrade head
uv run python frontend_client/e2e/reset_db.py open
exec uv run python -m app.main > frontend_client/e2e/.server.log 2>&1
