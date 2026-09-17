# TasKanLine

Система управления задачами для небольших команд, часть работы в которых выполняют ИИ-агенты.
Иерархия `Workspace → Team → Project → Task`, сохраняемые Views, а CLI и MCP-сервер входят в
продукт наравне с веб-интерфейсом: агент не «интегрируется через API», а работает в тех же
задачах, что и человек.

**Стек:** Python 3.13 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL 16 · React 19 · TypeScript · Vite · Tailwind

> Текущее состояние — **Этап 0 «Фундамент»**: работает каркас, бизнес-сущностей ещё нет.
> Полная документация — в `docs/superpowers/specs/` (симлинк на Obsidian-vault).

## Структура

```
backend/          FastAPI-приложение и миграции Alembic
frontend_client/  веб-клиент (Vite + React + TypeScript), светлая и тёмная темы
frontend_admin/   админ-панель: тот же стек, те же токены тем        — этап 6
sdk/              Python-клиент API, общий для CLI и MCP              — этап 7
cli/              CLI tkl                                             — этап 7
mcp/              MCP-сервер                                          — этап 8
deploy/           docker-compose, nginx, .env.example
docs/             спецификации (симлинк в Obsidian)
```

Python-часть — один uv-workspace: `uv sync` в корне поднимает окружение для всех четырёх пакетов
сразу. Фронтенд живёт отдельно на `bun`.

## Как поднять окружение с нуля

Нужны: [uv](https://docs.astral.sh/uv/), [bun](https://bun.sh/), Docker с плагином compose.

```bash
# 1. Python-окружение (uv сам скачает Python 3.13)
uv sync

# 2. Конфигурация
cp deploy/.env.example .env
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env

# 3. PostgreSQL для разработки
docker compose -f deploy/docker-compose.dev.yml up -d

# 4. Миграции
uv run alembic -c backend/alembic.ini upgrade head

# 5. API на http://localhost:8000
uv run uvicorn app.main:app --reload

# 6. Веб-клиент на http://localhost:5173 (в отдельном терминале)
cd frontend_client && bun install && bun run dev
```

Проверка: `curl localhost:8000/health` отдаёт `{"status":"ok","version":"0.1.0","database":"ok"}`.

## Весь стек в контейнерах

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

Поднимает `postgres`, `backend` (миграции применяются при старте контейнера) и `frontend_client` —
nginx со статикой и прокси на `/api/v1/*`. Веб-клиент на `http://localhost:8080`,
API на `http://localhost:8000`.

## Команды

| Что | Команда |
|---|---|
| Тесты бэкенда | `uv run pytest` |
| Линтер и формат Python | `uv run ruff check .` · `uv run ruff format .` |
| Типы Python | `uv run mypy backend` |
| Тесты фронтенда | `cd frontend_client && bun run test` |
| Линтер и типы фронтенда | `cd frontend_client && bun run lint && bun run typecheck` |
| Новая миграция | `uv run alembic -c backend/alembic.ini revision --autogenerate -m "описание"` |

Тестам нужен поднятый PostgreSQL: базу `taskanline_test` фикстура создаёт и мигрирует сама.
Другой адрес задаётся переменной `TEST_DATABASE_URL`.

## Конфигурация

Все переменные перечислены с комментариями в `deploy/.env.example` и разбираются
через pydantic-settings в `backend/app/core/config.py`. Обязательные — `DATABASE_URL`
(драйвер обязательно `asyncpg`) и `SECRET_KEY` от 32 символов.

## Темы оформления

Тёмная тема обязательна в обоих фронтендах. Выбор — `light`, `dark` или `system`
(по умолчанию системный), хранится в `localStorage`, применяется классом `dark` на `<html>`
встроенным скриптом до первой отрисовки — иначе тёмная страница мигает светлым.

Цвета в разметке задаются семантическими токенами — `bg-canvas`, `bg-surface`,
`bg-surface-hover`, `text-fg`, `text-fg-muted`, `border-border`, `text-accent`, — а не парами
вида `bg-white dark:bg-slate-900`. Сами токены живут в `frontend_client/src/index.css`
и на этапе 6 становятся общими с `frontend_admin`. Механика темы — в
`frontend_client/src/shared/theme/`.

## Разработка

Разработка ведётся по TDD и по этапам из
[дорожной карты](docs/superpowers/specs/2026-09-16-taskanline-roadmap.md): каждый этап
превращается в отдельный implementation plan, тест пишется первым и падает по нужной причине.
