# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) and other coding agents when working
with code in this repository. `CLAUDE.md` is a symlink to this file — правила одни на всех агентов.

## Язык

Код, комментарии, докстроки, сообщения коммитов и общение с пользователем — на русском.
Имена функций, переменных и тестов — на английском.

## Ветки

- `main` — релизная. Напрямую в неё не коммитить.
- `dev` — рабочая. Всё стекается сюда.
- Остальные — от `dev` и обратно в `dev`: `feat/…`, `fix/…`, `chore/…`, `docs/…`,
  `refactor/…`, `test/…`. После слияния ветку можно удалять.

**На каждую полученную задачу — новая ветка от `dev`.** Порядок: `git switch dev`,
`git switch -c feat/<короткий-слаг>`, работа, коммиты. Слияние в `dev` и релиз в `main` —
решение человека, самостоятельно не вливать и не пушить.

Если задача пришла, а HEAD стоит на `main` или на чужой ветке — переключиться на `dev` и
ответвиться от неё, а не продолжать там, где оказался.

## Спецификации — источник правды

Проект ведётся по семи утверждённым документам в `docs/superpowers/specs/` (симлинк на
Obsidian-vault, git его игнорирует). **Читать перед любой архитектурной работой**, порядок в
`docs/superpowers/specs/README.md`. Ключевые: `…-architecture.md`, `…-data-model.md`,
`…-roadmap.md`.

Документы живые: решение, изменённое в ходе реализации, правится в них же — не остаётся в
истории чата. Правка спеки идёт тем же изменением, что и код.

Работа разбита на **11 этапов** (roadmap). Этапы 0 «Фундамент» и 1 «Аутентификация и
пользователи» закрыты 2026-09-18; 2026-09-19 к ним добавилась клиентская половина этапа 1 —
вход, регистрация, профиль и страница токенов (часть пунктов этапа 5 досрочно). Следующий —
этап 2 «Организационная структура и права». Каждый
этап перед началом превращается в отдельный implementation plan через `superpowers:writing-plans`
и кладётся в `docs/superpowers/plans/`; разработка по TDD — тест пишется первым и падает по нужной
причине.

## Команды

Частое обёрнуто в `Makefile`: `make` покажет список целей. Ниже — что за ними стоит.

```bash
# Окружение (uv сам поставит Python 3.13)
uv sync
cp .env.example .env            # заполнить SECURITY__SECRET_KEY

# PostgreSQL для разработки и тестов
docker compose --env-file .env -f deploy/docker-compose.dev.yml up -d

# Миграции
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini revision --autogenerate -m "описание" --rev-id 0001
# или короче: make migration name=users_auth rev=0001
# rev= обязателен по смыслу: миграции в спеке пронумерованы подряд, без него будет хеш

# API (host/port/reload берутся из SERVER__*)
uv run python -m app.main

# Тесты
uv run pytest
uv run pytest backend/tests/test_config.py::TestDatabase::test_url_is_composed_from_parts
uv run pytest -k cors

# Линтеры и типы
uv run ruff check . && uv run ruff format . && uv run mypy backend

# Веб-клиент
cd frontend_client && bun install
bun run dev            # и так же: test, lint, typecheck, build
bun run vitest run src/shared/theme/theme.test.ts     # один файл тестов

# Весь стек в контейнерах
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

`--env-file .env` обязателен: project directory у compose — каталог compose-файла, корневой
`.env` он сам не найдёт.

## Структура

Монорепо: `backend/` (FastAPI), `frontend_client/` (React+Vite), `sdk/`, `cli/`, `mcp/` (пока
пустые пакеты, наполняются на этапах 7–8), `deploy/`, `docs/`. Админ-панель появится на этапе 6
как `frontend_admin/` — **не `admin/`**, как записано в старых частях спек.

Python-часть — один uv-workspace, корневой `pyproject.toml` держит и конфиги ruff/mypy/pytest.
Фронтенд живёт отдельно на bun.

## Архитектурные правила

Взяты из спецификаций; нарушать их молча нельзя.

- **Слои модуля.** Каждый модуль в `backend/app/modules/` устроен одинаково: `models.py`,
  `schemas.py`, `repository.py`, `service.py`, `router.py`. Сервис одного модуля может вызывать
  сервис другого, но **никогда его репозиторий**; роутер не обращается к репозиторию вообще.
- **Нет доступа → 404, а не 403.** 403 только когда объект виден, но действие запрещено ролью.
  Каждый запрос к БД фильтруется по `workspace_id`.
- **Формат ошибки один на всё API:** `{"error": {"code", "message", "details"}}`. Машиночитаемый
  `code` важнее текста — по нему ветвятся SDK, CLI и агент. Новые ошибки — через `ApiError` из
  `app/core/errors.py`.
- **Redis нет** и не будет до этапа 9. Кэш прав, распределённый rate limiting и очередь задач
  сознательно отложены; не добавлять «заодно».
- **Миграции применяются отдельной командой**, а не из кода приложения.
- Пагинация курсорная, не offset. Списки отдают плоские объекты с id, вложенность — только по
  `?expand=`.

## Настройки

`Settings` в `backend/app/core/config.py` собран из вложенных групп-`BaseModel`, и группа задаёт
префикс переменной окружения через двойное подчёркивание: `DB__`, `SECURITY__`, `APP__`, `CORS__`,
`SERVER__`, `LOG__`, `AUTH__`. Новая настройка добавляется **в группу**, а не плоским полем, и
обязательно попадает в `.env.example` — тест `TestEnvExample` падает, если поле забыто.

Параметры БД хранятся по частям (`DB__USER`, `DB__PASSWORD`, `DB__HOST`, `DB__PORT`, `DB__NAME`);
строку собирает свойство `DatabaseSettings.url` с экранированием логина и пароля. Пароль и
секретный ключ — `SecretStr`.

`AUTH__` — это политика сессий: время жизни пары токенов, флаги cookie и лимиты на перебор.
Секрет подписи остаётся в `SECURITY__`; смешивать их не надо.

Тесты берут подключение из тех же `DB__*` и подменяют только имя базы через `TEST_DB_NAME`.
`POSTGRES_PORT` — это порт публикации контейнера на хост, он не связан с `DB__PORT` внутри сети
compose; при занятом 5432 менять оба. `AUTH__COOKIE_SECURE` в тестах принудительно выключен:
тестовый клиент ходит по http, и Secure-cookie по нему не отправляется.

## Аутентификация

Два способа доказать, кто ты, и одна абстракция поверх них — `Principal` из
`backend/app/core/principal.py`. Человек приходит с cookie-сессией (`tkl_access` — подписанный JWT,
`tkl_refresh` — непрозрачный токен, хеш которого лежит в `refresh_tokens`), агент — с PAT в
`Authorization: Bearer tkl_…`. Дальше по коду разницы нет: эндпоинт зависит от `CurrentPrincipal`
или `WritePrincipal`, а не от того, откуда взялись учётные данные.

Что важно не сломать:

- **Токен агента проверяется раньше cookie.** Иначе ограничение `scope = read` обходится случайной
  сессией в том же браузере.
- **Мутирующий эндпоинт вешается на `WritePrincipal`**, а не на `CurrentPrincipal`: именно там
  проверяется `scope` и возвращается `403 insufficient_scope`.
- **CSRF закрыт middleware** `CsrfMiddleware`: мутация с cookie сессии и без `Authorization`
  требует заголовка `X-Requested-With: XMLHttpRequest`. Новый эндпоинт попадает под проверку сам —
  добавлять ничего не нужно.
- **Чужой объект отвечает 404, а не 403** — это уже действует для `DELETE /me/tokens/{id}`.
- **Rate limiting** живёт в `app.state.rate_limiter` (экземпляр на приложение) и вешается
  зависимостью `rate_limit(...)` из `core/rate_limit.py`.

Потеря доступа лечится командой, работающей с базой напрямую:

```bash
uv run python -m app.admin grant --email ivan@example.com --role superadmin
```

## Тесты

Основная масса — интеграционные, через `httpx.AsyncClient` поверх ASGI-приложения и **реальную
PostgreSQL**. Фикстура `db_connection` держит внешнюю транзакцию и откатывает её после каждого
теста; `test_db_isolation.py` проверяет, что откат действительно работает. Миграции затребованы
фикстурой, а не autouse, — тесты чистых функций идут без базы.

Обязательный набор на права (с этапа 2): для каждого защищённого эндпоинта тест на 404 чужаку и
403 при недостаточной роли; для админских — 404 обычному пользователю и `403 session_required`
для PAT.

`asyncio_default_fixture_loop_scope = "function"` в `pyproject.toml` менять нельзя: соединение
asyncpg, открытое в чужом цикле событий, падает с «attached to a different loop».

## Фронтенд

Тёмная тема обязательна и в `frontend_client`, и в будущем `frontend_admin`. Цвета задаются
семантическими токенами (`bg-canvas`, `bg-surface`, `bg-surface-hover`, `text-fg`, `text-fg-muted`,
`border-border`, `text-accent`) из `src/index.css` — **не парами `bg-white dark:bg-slate-900`**.
Механика в `src/shared/theme/`: выбор `light`/`dark`/`system`, класс `dark` на `<html>`, скрипт
против мигания в `index.html`.

**Типы API генерируются из OpenAPI — руками не писать.** `src/shared/api/schema.d.ts` собирает
`make api-types` (она же снимает схему с приложения через `python -m app.openapi`). Правка этого
файла руками живёт до следующей генерации, а джоба CI `api-types` пересобирает его и падает на
расхождении. `bun run generate:api` — вторая половина той же команды: пересобирает типы из уже
сохранённого `openapi.json`, без Python.

Структура по архитектуре §4.2: `routes/` — файловая маршрутизация (дерево `src/routeTree.gen.ts`
генерирует плагин, руками не править), `features/<домен>/{api,components,model}`, `shared/{api,ui,lib}`,
`app/` — провайдеры и оболочка. Импорты между каталогами — через алиас `@/`.

**Весь HTTP идёт через `shared/api/client.ts`.** Свой `fetch` мимо него не пройдёт защиту от CSRF:
заголовок `X-Requested-With` ставится там на каждый запрос, иначе бэкенд отвечает
`403 csrf_required`. Там же разбор конверта ошибки в `ApiError` и обновление протухшей сессии —
одно на все параллельные `401`, чтобы два запроса не предъявили один refresh-токен и не уронили
все сессии пользователя. Текст для человека — `humanMessage(error)` по коду ошибки,
`fieldErrors(error)` раскладывает `422` по полям формы.

Сессия — запрос `GET /me` под ключом `['session']`; защита маршрутов живёт в `beforeLoad` ветки
`routes/_authed.tsx`, а не внутри экранов. Мутирующая кнопка проверяет `canWrite(session)`: под
токеном со `scope = read` сервер всё равно ответит `403`.

Компоненты `shared/ui/` перенесены из shadcn/ui руками и переписаны на токены проекта. CLI shadcn
не запускать: он перепишет `index.css` под свой набор токенов.

Тесты — Vitest с MSW (`src/test/msw/`), сеть закрыта (`onUnhandledRequest: 'error'`). Два теста в
одном файле, открывающих меню или окно Radix, мешают друг другу: перехватчик указателя от
размонтированного меню съедает первое нажатие в следующем тесте. Vitest изолирует файлы, но не
тесты внутри файла — такие сценарии разносить по файлам.

## Мелочи, на которых легко споткнуться

- В ruff отключены `RUF001–003`: они ругаются на кириллицу в комментариях и дают только шум.
- `mypy` в строгом режиме покрывает только `backend`; `sdk`/`cli`/`mcp` попадут под него на своих
  этапах.
- Remote на GitHub пока нет — CI в `.github/workflows/ci.yml` написан, но на PR не прогонялся.
