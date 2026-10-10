# 1. Установка и запуск

Есть два пути: **весь стек в Docker** — чтобы пользоваться, и **локальная разработка** — чтобы
менять код. Начать с любого.

## Что нужно

| Инструмент | Зачем | Проверка |
|---|---|---|
| [Docker](https://docs.docker.com/get-docker/) с плагином compose | PostgreSQL, а в первом варианте — весь стек | `docker compose version` |
| [uv](https://docs.astral.sh/uv/) | Python-окружение; Python 3.13 он скачает сам | `uv --version` |
| [bun](https://bun.sh/) | сборка и dev-сервер веб-клиента и админки | `bun --version` |
| `openssl` | сгенерировать секретный ключ | `openssl version` |

Для варианта «только Docker» достаточно Docker; uv понадобится, если захочется CLI или MCP.

## Конфигурация: файл `.env`

Все настройки — переменные окружения из файла `.env` в корне репозитория. Шаблон с
комментариями к каждой — `.env.example`:

```bash
cp .env.example .env
sed -i "s/^SECURITY__SECRET_KEY=.*/SECURITY__SECRET_KEY=$(openssl rand -hex 32)/" .env
```

Обязательно заполнить только `SECURITY__SECRET_KEY` (не короче 32 символов) — им подписываются
сессии и ссылки-приглашения. Остальное работает как есть. Что стоит знать:

| Переменная | По умолчанию | Когда менять |
|---|---|---|
| `DB__USER`, `DB__PASSWORD`, `DB__HOST`, `DB__PORT`, `DB__NAME` | `taskanline` на `localhost:5432` | своя база; в docker-compose хост — `postgres` |
| `POSTGRES_PORT` | `5432` | порт 5432 на машине занят — поменяйте и его, и `DB__PORT` |
| `APP__PUBLIC_URL` | `http://localhost:5173` | внешний адрес клиента: из него строятся ссылки в письмах |
| `CORS__ORIGINS` | `http://localhost:5173` | клиент открывается с другого адреса |
| `MAILER__BACKEND` | `console` | `smtp` — отправлять письма по-настоящему (`MAILER__HOST`, `…PORT`, `…USERNAME`, `…PASSWORD`) |
| `AUTH__COOKIE_SECURE` | `false` | на продакшене за HTTPS — `true` |
| `AUTH__COOKIE_DOMAIN` | пусто | клиент и админка на разных поддоменах одного домена |
| `SERVER__FORWARDED_ALLOW_IPS` | `127.0.0.1` | за nginx — адрес прокси, иначе журнал аудита видит прокси, а не человека |

С `MAILER__BACKEND=console` письма не уходят, а целиком пишутся в лог API событием
`mail.console` — оттуда берётся ссылка-приглашение, пока SMTP не настроен.

## Вариант А. Весь стек в Docker

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
# то же самое: make stack-up
```

Поднимутся четыре контейнера; миграции база получает сама при старте `backend`.

| Адрес | Что |
|---|---|
| http://localhost:8080 | веб-клиент |
| http://localhost:8081 | админ-панель |
| http://localhost:8000 | API (`/health` — проверка, `/docs` — OpenAPI) |

`--env-file .env` обязателен: compose ищет `.env` рядом с compose-файлом, а не в корне.
Остановить — `make stack-down`.

Перед выкладкой наружу: в `deploy/nginx/admin.conf` впишите сети, из которых можно открывать
админку; поставьте `AUTH__COOKIE_SECURE=true` и настоящие `APP__PUBLIC_URL`, `CORS__ORIGINS`.

## Вариант Б. Локальная разработка

```bash
# 1. Зависимости Python и обоих фронтендов
uv sync
(cd frontend_client && bun install)
(cd frontend_admin && bun install)

# 2. .env — см. выше

# 3. PostgreSQL в контейнере
make db-up             # docker compose --env-file .env -f deploy/docker-compose.dev.yml up -d

# 4. Миграции — отдельной командой, приложение само их не применяет
make migrate           # uv run alembic -c backend/alembic.ini upgrade head

# 5. API на http://localhost:8000
make run               # uv run python -m app.main

# 6. Веб-клиент на http://localhost:5173 — во втором терминале
cd frontend_client && bun run dev

# 7. Админ-панель на http://localhost:5175 — в третьем
cd frontend_admin && bun run dev
```

Проверка: `curl localhost:8000/health` отвечает
`{"status":"ok","version":"0.1.0","database":"ok"}`, а http://localhost:5173 открывает экран
входа. Dev-серверы проксируют `/api` на `localhost:8000`, поэтому клиент и админка делят одну
сессию.

`SERVER__RELOAD=true` в `.env` перезапускает API при правке кода.

## Первый вход

1. Откройте клиент и нажмите «Зарегистрироваться». Пустой сервер открыт для первой
   регистрации, и **первый зарегистрировавшийся становится `superadmin`** инстанса.
2. После этого регистрация по умолчанию — **только по приглашению**. Открыть её для всех или
   ограничить доменами почты — в админ-панели, раздел «Настройки».
3. Создайте рабочее пространство — клиент предложит это сам ([подробнее](02-client.md#первое-пространство)).

Завести пользователя прямо в базе, минуя регистрацию и её политику, — например, на закрытом
инстансе:

```bash
make create-user       # спросит email, имя, роль инстанса и пароль
```

## Если доступ потерян

Единственный `superadmin` забыл пароль или заблокирован — роль назначается командой на сервере,
ей нужна только база из `.env`:

```bash
uv run python -m app.admin grant --email anna@acme.example --role superadmin
```

В Docker — то же внутри контейнера:
`docker compose --env-file .env -f deploy/docker-compose.yml exec backend python -m app.admin grant --email … --role superadmin`.

## Тесты и проверки

| Что | Команда |
|---|---|
| Все тесты (бэкенд, SDK, CLI, MCP, веб-клиент) | `make test` |
| Только бэкенд, с аргументами pytest | `make test-back a="-k cors"` |
| Сценарии в браузере (Playwright) | `bunx playwright install chromium` один раз, затем `make test-e2e` |
| Линтеры и типы | `make lint` |
| Пересобрать скриншоты этого руководства | `make docs-screenshots` |

Тесты бэкенда ходят в настоящий PostgreSQL, но в отдельную базу `taskanline_test`, а
Playwright — в `taskanline_e2e` на порту 8001; рабочую базу и запущенные серверы они не
трогают.

## Частые проблемы

| Симптом | Причина и решение |
|---|---|
| `port is already allocated` при `make db-up` | 5432 занят системным PostgreSQL: поменяйте `POSTGRES_PORT` и `DB__PORT` |
| compose не видит переменных | забыт `--env-file .env` — используйте цели `make` |
| `403 csrf_required` из своего скрипта | мутирующий запрос с cookie-сессией требует `X-Requested-With: XMLHttpRequest`; агентам удобнее токен |
| вход проходит, но сразу выкидывает | открыли по `http`, а `AUTH__COOKIE_SECURE=true` — cookie с флагом Secure по http не отправляется |
| письмо-приглашение не пришло | `MAILER__BACKEND=console`: ссылка лежит в логе API (`mail.console`) |
| в журнале аудита у всех адрес `172.…` | API за прокси: задайте `SERVER__FORWARDED_ALLOW_IPS` |
