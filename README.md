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
deploy/           docker-compose и конфигурация nginx
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
cp .env.example .env
sed -i "s/^SECURITY__SECRET_KEY=.*/SECURITY__SECRET_KEY=$(openssl rand -hex 32)/" .env

# 3. PostgreSQL для разработки
docker compose --env-file .env -f deploy/docker-compose.dev.yml up -d

# 4. Миграции
uv run alembic -c backend/alembic.ini upgrade head

# 5. API на http://localhost:8000 (SERVER__RELOAD=true — автоперезапуск при правке)
uv run python -m app.main

# 6. Веб-клиент на http://localhost:5173 (в отдельном терминале)
cd frontend_client && bun install && bun run dev
```

Проверка: `curl localhost:8000/health` отдаёт `{"status":"ok","version":"0.1.0","database":"ok"}`,
а `http://localhost:5173/` открывает экран входа. Запросы клиента к `/api` dev-сервер проксирует
на бэкенд, так что cookie сессии остаются в пределах одного origin.

`--env-file .env` обязателен: без него compose не видит переменные из корневого `.env`,
потому что project directory у него — каталог compose-файла. Если порт 5432 на хосте занят
системным PostgreSQL, поменяй в `.env` и `POSTGRES_PORT`, и `DB__PORT`.

## Весь стек в контейнерах

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

Поднимает `postgres`, `backend` (миграции применяются при старте контейнера) и `frontend_client` —
nginx со статикой и прокси на `/api/v1/*`. Веб-клиент на `http://localhost:8080`,
API на `http://localhost:8000`.

## Команды

Частое собрано в `Makefile` — `make` без аргументов покажет список:

| Что | Make | Полная команда |
|---|---|---|
| Запустить API | `make run` | `uv run python -m app.main` |
| Поднять и погасить БД | `make db-up` · `make db-down` | `docker compose --env-file .env -f deploy/docker-compose.dev.yml up -d` |
| Все тесты | `make test` | — |
| Тесты бэкенда с аргументами | `make test-back a="-k cors"` | `uv run pytest -k cors` |
| Линтеры и типы | `make lint` · `make format` | — |
| Применить миграции | `make migrate` | `uv run alembic -c backend/alembic.ini upgrade head` |
| Создать миграцию | `make migration name=users_auth rev=0001` | `… revision --autogenerate -m … --rev-id …` |
| Откатить последнюю | `make migrate-down` | `… downgrade -1` |
| Типы клиента из OpenAPI | `make api-types` | `uv run python -m app.openapi > frontend_client/openapi.json` + `bun run generate:api` |
| Весь стек в контейнерах | `make stack-up` · `make stack-down` | — |

`rev=` задаёт идентификатор ревизии: без него alembic подставит случайный хеш, а миграции
в спецификации пронумерованы подряд — `0001_users_auth`, `0002_org`.

Полный список:

| Что | Команда |
|---|---|
| Тесты бэкенда | `uv run pytest` |
| Линтер и формат Python | `uv run ruff check .` · `uv run ruff format .` |
| Типы Python | `uv run mypy backend` |
| Тесты фронтенда | `cd frontend_client && bun run test` |
| Линтер и типы фронтенда | `cd frontend_client && bun run lint && bun run typecheck` |
| Новая миграция | `uv run alembic -c backend/alembic.ini revision --autogenerate -m "описание"` |

Тестам нужен поднятый PostgreSQL: подключение берётся из тех же `DB__*`, а имя базы
подменяется на `TEST_DB_NAME` (по умолчанию `taskanline_test`) — фикстура создаёт её
и накатывает миграции сама. Гонять тесты по рабочей базе нельзя даже случайно.

## Конфигурация

Все переменные перечислены с комментариями в `.env.example` и разбираются
через pydantic-settings в `backend/app/core/config.py`.

Настройки сгруппированы по областям — по одной модели на группу, и группа задаёт префикс
переменной через двойное подчёркивание:

| Группа | Префикс | Что внутри |
|---|---|---|
| `DatabaseSettings` | `DB__` | `USER`, `PASSWORD`, `NAME` — обязательны; `DRIVER`, `HOST`, `PORT` — с умолчаниями |
| `SecuritySettings` | `SECURITY__` | `SECRET_KEY` — обязателен, от 32 символов |
| `AuthSettings` | `AUTH__` | время жизни пары токенов, флаги cookie, лимиты на перебор |
| `AppSettings` | `APP__` | `ENVIRONMENT`, `PUBLIC_URL` |
| `CorsSettings` | `CORS__` | `ORIGINS`, `ALLOW_CREDENTIALS`, `ALLOW_METHODS`, `ALLOW_HEADERS` |
| `ServerSettings` | `SERVER__` | `HOST`, `PORT`, `RELOAD` |
| `LogSettings` | `LOG__` | `LEVEL` |

В коде они читаются так же: `settings.db.user`, `settings.security.secret_key`,
`settings.log.level`. Строка подключения собирается из частей — `settings.db.url`, — и логин
с паролем при этом экранируются: двоеточие или собака в пароле иначе разваливают URL.
Списки (`CORS__*`) принимают и строку через запятую, и JSON-массив.

Приложение запускается как модуль: `python -m app.main` читает `SERVER__HOST`, `SERVER__PORT`
и `SERVER__RELOAD` и поднимает uvicorn сам — отдельной команды `uvicorn` с дублирующими
флагами нет.

## Аутентификация

Человек работает через cookie-сессию, агент — через персональный токен доступа (PAT).

```bash
# Регистрация. Первый зарегистрировавшийся получает роль инстанса superadmin.
curl -s -c tkl.jar -H 'X-Requested-With: XMLHttpRequest' -H 'Content-Type: application/json' \
  -d '{"email":"ivan@example.com","password":"correct horse battery","full_name":"Иван"}' \
  http://localhost:8000/api/v1/auth/register

# Выпуск токена для агента. Полное значение показывается ровно один раз.
curl -s -b tkl.jar -H 'X-Requested-With: XMLHttpRequest' -H 'Content-Type: application/json' \
  -d '{"name":"claude-code","scope":"read"}' http://localhost:8000/api/v1/me/tokens

# Запрос от имени агента
curl -s -H "Authorization: Bearer tkl_…" http://localhost:8000/api/v1/me
```

`scope=read` даёт только чтение: любая мутация отвечает `403 insufficient_scope`. Мутирующий
запрос с cookie-сессией обязан нести заголовок `X-Requested-With: XMLHttpRequest` — без него
ответ `403 csrf_required`. Токены хранятся в базе только хешем, потерянный токен не
восстанавливается — выпускается новый.

Если доступ к единственному `superadmin` потерян, роль назначается с сервера:

```bash
uv run python -m app.admin grant --email ivan@example.com --role superadmin
```

То же самое доступно в браузере: `http://localhost:5173/` уводит на экран входа, оттуда —
регистрация, а токены выпускаются и отзываются на странице «Токены доступа» в меню профиля.
Полное значение токена показывается один раз, сразу после выпуска.

## Веб-клиент

React + TypeScript на Vite; маршрутизация TanStack Router (файловая, `src/routes/`), запросы —
TanStack Query, формы — React Hook Form с Zod.

**Типы API не пишутся руками.** `src/shared/api/schema.d.ts` генерируется из OpenAPI-схемы
бэкенда командой `make api-types` и лежит в git; отдельная джоба CI пересобирает его и падает,
если он разошёлся со схемой. После правки роутеров или Pydantic-схем бэкенда — перегенерировать.

Весь HTTP идёт через `src/shared/api/client.ts`: cookie, обязательный заголовок
`X-Requested-With`, разбор ошибок и обновление протухшей сессии собраны там. Свой `fetch` в
обход него получит `403 csrf_required` на первой же мутации.

```bash
cd frontend_client
bun run dev        # http://localhost:5173, /api проксируется на localhost:8000
bun run test       # Vitest с MSW: сеть в тестах закрыта
bun run lint && bun run typecheck && bun run build
```

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
