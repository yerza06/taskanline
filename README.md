# TasKanLine

Система управления задачами для небольших команд, часть работы в которых выполняют ИИ-агенты.
Иерархия `Workspace → Team → Project → Task`, сохраняемые Views, а CLI и MCP-сервер входят в
продукт наравне с веб-интерфейсом: агент не «интегрируется через API», а работает в тех же
задачах, что и человек.

**Стек:** Python 3.13 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL 16 · React 19 · TypeScript · Vite · Tailwind

> Текущее состояние — закрыты **этапы 0–8**: каркас, аутентификация и PAT-токены, рабочие
> пространства/команды/проекты с приглашениями по почте и правами трёх уровней, ядро задач
> (ключи `ENG-142`, статусы, метки, подзадачи, связи, комментарии, история, уведомления),
> сохраняемые Views, веб-клиент (задачи списком и доской, карточка, views, участники), Python-SDK,
> CLI `tkl` и MCP-сервер `tkl-mcp` для агентов, админ-панель инстанса. Дальше — Redis (этап 9,
> по необходимости) и интеграции с GitHub и GitLab (этап 10). Полная документация — в `docs/superpowers/specs/` (симлинк на Obsidian-vault).

## Структура

```
backend/          FastAPI-приложение и миграции Alembic
frontend_client/  веб-клиент (Vite + React + TypeScript), светлая и тёмная темы
frontend_admin/   админ-панель инстанса: отдельное приложение и хост
frontend_shared/  токены темы, общие для обоих фронтендов
sdk/              Python-клиент API, общий для CLI и MCP
cli/              CLI tkl для агентов и терминала
mcp/              MCP-сервер tkl-mcp для Claude, ChatGPT и других клиентов
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
| `MailSettings` | `MAILER__` | `BACKEND` (`console`/`smtp`), `HOST`, `PORT`, `USERNAME`, `PASSWORD`, `FROM_ADDRESS` |
| `InvitationSettings` | `INVITE__` | `TTL_DAYS`, лимит на `POST /invitations` (`ATTEMPTS`, `WINDOW_SECONDS`) |

В коде они читаются так же: `settings.db.user`, `settings.security.secret_key`,
`settings.log.level`. Строка подключения собирается из частей — `settings.db.url`, — и логин
с паролем при этом экранируются: двоеточие или собака в пароле иначе разваливают URL.
Списки (`CORS__*`) принимают и строку через запятую, и JSON-массив.

Приложение запускается как модуль: `python -m app.main` читает `SERVER__HOST`, `SERVER__PORT`
и `SERVER__RELOAD` и поднимает uvicorn сам — отдельной команды `uvicorn` с дублирующими
флагами нет.

По умолчанию (`MAILER__BACKEND=console`) письмо не отправляется, а целиком пишется в лог API
структурным событием `mail.console` — так на машине разработчика, где нет SMTP, всё равно можно
увидеть ссылку `/invite/<token>` из приглашения и открыть её в браузере.

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

## CLI `tkl`

```bash
uv tool install ./cli                     # из репозитория; бинарь — tkl
tkl auth login --token tkl_… --api-url http://localhost:8000
tkl config set team ENG                   # команда по умолчанию

tkl team states ENG                       # какие статусы есть — до любых изменений
tkl task list --filter "assignee:me state-type:started"
tkl task state ENG-142 "In Progress"
tkl task comment ENG-142 -m "Исправлено в PR #218"
tkl task close ENG-142
tkl view run "Мои незакрытые баги"
```

Вывод — таблица в терминале и JSON при перенаправлении (`tkl task list > tasks.json`). Коды
выхода различают ошибки: 3 — нет доступа, 4 — не найдено, 6 — rate limit, 7 — сеть. Полное
описание — в CLI-спеке (`docs/superpowers/specs/…-cli-spec.md`).

## MCP-сервер `tkl-mcp`

Даёт модели инструменты трекера прямо в диалоге: `list_teams`, `search_tasks`, `get_task`,
`run_view`, `create_task`, `update_task_state`, `comment_task` и другие. Конфиг общий с `tkl`:
после `tkl auth login` сервер готов.

```bash
uv tool install ./mcp                      # бинарь tkl-mcp
```

Claude Desktop (`claude_desktop_config.json`) или Claude Code (`.mcp.json`):

```json
{
  "mcpServers": {
    "taskanline": {"command": "tkl-mcp", "args": ["--profile", "work"]}
  }
}
```

Только чтение — `"args": ["--read-only"]` и токен со `scope=read`: инструменты записи исчезают
из каталога, а токен не даст ничего изменить, даже если флаг забыли. `--workspace acme` прячет
остальные пространства.

Удалённый режим для claude.ai и ChatGPT — `tkl-mcp --transport http --port 8765
--allowed-host mcp.example.com` за HTTPS-прокси; клиент подключается к
`https://mcp.example.com/mcp` и передаёт свой токен заголовком `Authorization: Bearer`.

## Админ-панель

Управление сервером, а не задачами: люди (блокировка, сброс пароля, роли инстанса, удаление),
рабочие пространства (счётчики, удаление, аварийная передача владения), политика регистрации и
журнал аудита. Содержимого пространств — задач, комментариев, описаний — панель не показывает.

```bash
cd frontend_admin && bun install && bun run dev    # http://localhost:5175, та же сессия, что у клиента
```

- Входят роли инстанса `support`, `admin`, `superadmin`; первый зарегистрировавшийся —
  `superadmin`. Обычный пользователь получает «не найдено», токен агента — `403 session_required`.
- Опасные действия (роль, удаление, настройки, передача владения) подтверждаются паролем — окно
  на 15 минут.
- Регистрация по умолчанию **только по приглашению**; открыть её или ограничить доменами —
  в настройках. Пустой сервер открыт для первой регистрации.
- В docker-compose админка — отдельный контейнер на порту 8081 с конфигом
  `deploy/nginx/admin.conf`: впишите туда сети, из которых её можно открывать. Клиент и админка
  на разных доменах делят сессию через `AUTH__COOKIE_DOMAIN`.

Если доступ к единственному `superadmin` потерян, роль назначается с сервера:

```bash
uv run python -m app.admin grant --email ivan@example.com --role superadmin
```

То же самое доступно в браузере: `http://localhost:5173/` уводит на экран входа, оттуда —
регистрация, а токены выпускаются и отзываются на странице «Токены доступа» в меню профиля.
Полное значение токена показывается один раз, сразу после выпуска.

## Веб-клиент

React + TypeScript на Vite; маршрутизация TanStack Router (файловая, `src/routes/`), запросы —
TanStack Query, формы — React Hook Form с Zod, перетаскивание — dnd-kit, UI-состояние — Zustand.

Что есть: пространства с боковым меню, задачи команды, проекта и «мои» — списком и доской
(перетаскивание мышью и с клавиатуры), карточка задачи с Markdown, подзадачами, связями,
обсуждением и историей, конструктор фильтров и сохранённые views, участники и приглашения на
трёх уровнях, настройки команды, входящие. Горячие клавиши: `c` — новая задача, `/` — поиск,
`g t` / `g i` / `g m` — команда, входящие, мои задачи, `?` — справка.

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
bun run test:e2e   # Playwright: сценарии А–В против настоящего бэкенда (нужен make db-up)
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

Палитра чёрно-белая: ни одного оттенка, только светлота. Акцент — это инверсия фона, а не
другой цвет, поэтому опасное действие и сообщение об ошибке отличаются весом — границей,
насыщенностью текста, инверсией под курсором, — а не красным.

Шрифты подключены пакетами `@fontsource-variable/*` и лежат в сборке, без обращений к внешнему
CDN: **Inter** (`font-sans`) — весь интерфейс, **Raleway** (`font-display`) — название продукта
и заголовки экранов.

## Разработка

Перед первым `test:e2e` — `bunx playwright install chromium`. Прогон поднимает свой бэкенд на
базе `taskanline_e2e` (пересоздаётся каждый раз) и порту 8001, так что рабочей базе и серверу
на 8000/5173 не мешает.

Разработка ведётся по TDD и по этапам из
[дорожной карты](docs/superpowers/specs/2026-09-16-taskanline-roadmap.md): каждый этап
превращается в отдельный implementation plan, тест пишется первым и падает по нужной причине.
