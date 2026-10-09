# Короткие команды разработки. Подробности — в README.md.
# Список целей: make (или make help)

COMPOSE := docker compose --env-file .env
DEV_STACK := $(COMPOSE) -f deploy/docker-compose.dev.yml
FULL_STACK := $(COMPOSE) -f deploy/docker-compose.yml
ALEMBIC := uv run alembic -c backend/alembic.ini
FRONT := frontend_client

.DEFAULT_GOAL := help
.PHONY: help install env run db-up db-down db-logs stack-up stack-down \
        test test-back test-front test-e2e docs-screenshots lint format api-types \
        migrate migration migrate-down history create-user

help: ## Показать список команд
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
	| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'

# --- Окружение ---------------------------------------------------------------

install: env ## Поставить зависимости Python и фронтенда
	uv sync
	cd $(FRONT) && bun install

env: .env ## Создать .env из примера, если его ещё нет

.env:
	cp .env.example .env
	@echo "Создан .env — заполни SECURITY__SECRET_KEY: openssl rand -hex 32"

# --- Запуск ------------------------------------------------------------------

run: ## Запустить API (host, port и reload берутся из SERVER__*)
	uv run python -m app.main

db-up: env ## Поднять PostgreSQL для разработки и тестов
	$(DEV_STACK) up -d

db-down: ## Остановить PostgreSQL разработки
	$(DEV_STACK) down

db-logs: ## Логи PostgreSQL разработки
	$(DEV_STACK) logs -f postgres

stack-up: env ## Собрать и поднять весь стек в контейнерах
	$(FULL_STACK) up -d --build

stack-down: ## Остановить весь стек
	$(FULL_STACK) down

create-user: ## Добавить пользователя в базу (спросит email, имя, роль и пароль)
	uv run python backend/scripts/create_user.py

# --- Тесты и проверки --------------------------------------------------------

test: test-back test-front ## Прогнать все тесты

test-back: ## Тесты бэкенда. Аргументы: make test-back a="-k cors"
	uv run pytest $(a)

test-front: ## Тесты веб-клиента. Аргументы: make test-front a="src/app"
	cd $(FRONT) && bun run vitest run $(a)

test-e2e: ## Сценарии А–В в браузере (Playwright, своя база taskanline_e2e; нужен make db-up)
	cd $(FRONT) && bun run test:e2e

docs-screenshots: ## Пересобрать скриншоты docs/guide/images (Playwright, база taskanline_e2e; нужен make db-up)
	cd $(FRONT) && bun run docs:screenshots

lint: ## Линтеры и проверка типов на обеих половинах
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy backend sdk cli mcp
	cd $(FRONT) && bun run lint && bun run typecheck

format: ## Отформатировать и починить автоисправимое
	uv run ruff check --fix .
	uv run ruff format .

api-types: ## Пересобрать типы обоих фронтендов из OpenAPI бэкенда
	uv run python -m app.openapi > $(FRONT)/openapi.json
	cd $(FRONT) && bun run generate:api
	cd frontend_admin && bun run generate:api

# --- Миграции ----------------------------------------------------------------

migrate: ## Применить миграции до последней
	$(ALEMBIC) upgrade head

migration: ## Создать миграцию: make migration name=users_auth rev=0001
	@test -n "$(name)" || { echo 'Нужно имя: make migration name=users_auth rev=0001'; exit 1; }
	@test -n "$(rev)" || echo 'Без rev= идентификатор будет случайным хешем, а спека нумерует миграции подряд'
	$(ALEMBIC) revision --autogenerate -m "$(name)" $(if $(rev),--rev-id "$(rev)",)
	@echo "Сгенерированную ревизию нужно прочитать глазами: автогенерация не видит"
	@echo "переименований и переносов данных."

migrate-down: ## Откатить последнюю миграцию
	$(ALEMBIC) downgrade -1

history: ## Показать историю миграций и текущую ревизию
	$(ALEMBIC) history --verbose
	$(ALEMBIC) current
