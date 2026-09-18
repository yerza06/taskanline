# Клиентская часть аутентификации — Implementation Plan

> **Для исполнителя:** реализовывать по `superpowers:executing-plans`, задача за задачей.
> Шаги отмечены чекбоксами. Разработка по TDD: тест пишется первым и падает по нужной причине.

## Context

Этап 1 «Аутентификация и пользователи» закрыт на бэкенде и влит в `main`: работают
`POST /api/v1/auth/{register,login,refresh,logout}` с httpOnly-cookie, `GET/PATCH /api/v1/me`,
`GET/POST/DELETE /api/v1/me/tokens`, CSRF-заголовок и rate limiting. Проверить это можно только
через `curl`: в `frontend_client/` лежит каркас этапа 0 — статическая оболочка с переключателем
темы, без маршрутизации, без слоя запросов и без единого экрана.

Задача — клиентская половина того же этапа: человек регистрируется, входит, правит профиль и
выпускает себе PAT в браузере, а не в терминале. Это первый раз, когда продукт становится
пригодным к ручной проверке целиком.

Roadmap отдаёт веб-клиент этапу 5, который зависит от этапов 3–4 (задачи и views). Но пункты
«Экраны входа и регистрации», «Страница управления PAT», «Генерация типов из OpenAPI»,
«Маршрутизация TanStack Router» и «Слой запросов на TanStack Query» зависят только от этапа 1 и
делаются досрочно — иначе инфраструктура клиента будет вводиться посреди работы над досками.
Экранов задач, проектов и views здесь нет и не появляется.

**Спецификации (источник правды):**
- `docs/superpowers/specs/2026-09-16-taskanline-architecture.md` — §3.3 Principal и CSRF,
  §3.6 контракт API и формат ошибки, §4.1 стек, §4.2 структура, §4.4 темы, §4.5 без realtime
- `docs/superpowers/specs/2026-09-16-taskanline-roadmap.md` — «Этап 5», чеклист
- `docs/superpowers/specs/2026-09-16-taskanline-vision.md` — сценарий А

**Решения, принятые сверх спеки** (внести в спеки в последней задаче):
1. Часть пунктов этапа 5 выполняется досрочно, вместе с клиентской частью этапа 1.
2. **Zustand не вводится.** На auth-срезе нет ни одного состояния UI, переживающего
   размонтирование: тема уже живёт в своём контексте, остальное локально. Появится на этапе 5,
   когда появятся выделенные задачи и открытые панели.
3. **shadcn/ui копируется руками, без CLI.** `npx shadcn init` переписывает `index.css` под свой
   набор токенов (`--background`, `--primary`), а у проекта есть собственный, заданный в §4.4.
   Два словаря токенов в одном файле — гарантированный рассинхрон тем. Берём у shadcn то, ради
   чего он выбран: примитивы Radix и структуру компонента, — и выражаем классы через свои токены.
4. **Обновление сессии — в http-клиенте, а не в компонентах.** Любой `401` вызывает один
   `POST /auth/refresh` (single-flight) и повтор исходного запроса; неудача гасит кэш и уводит на
   `/login`. Компоненты про access-токен не знают вообще.
5. `bun run generate:api` генерирует типы из **уже сохранённого** `openapi.json`; схему из FastAPI
   выгружает `make api-types`. У фронтенда нет Python, и вызывать `uv` из bun-скрипта значит
   сделать `bun run generate:api` неработающим в CI-джобе веб-клиента.

## Global Constraints

- Ветка: от `dev`, называется `feat/client-auth`. В `dev` и `main` не вливать — решение человека.
- Комментарии, докстроки, сообщения коммитов, тексты интерфейса — на русском; имена в коде и
  тестах — на английском.
- **Типы API не пишутся руками** (AGENTS.md): только генерация из OpenAPI.
- Цвета — семантическими токенами из `src/index.css` (`bg-canvas`, `bg-surface`, `text-fg`,
  `text-fg-muted`, `border-border`, `text-accent`), не парами `bg-white dark:bg-slate-900`.
  Новый токен добавляется в оба блока (`:root` и `.dark`) сразу.
- Каждый экран проверяется в обеих темах и на ширине 360px.
- Доступность: у каждого поля `<label>`, ошибки связаны через `aria-describedby`, у формы
  `aria-invalid`, в модальных окнах фокус-ловушка (даёт Radix), навигация с клавиатуры.
- Тесты — Vitest + Testing Library поверх MSW; запросы в тестах не ходят в сеть,
  `onUnhandledRequest: 'error'`.
- Коммит после каждой задачи; `bun run lint && bun run typecheck && bun run test` зелёные перед
  коммитом.

---

## Подготовка

```bash
git switch dev
git switch -c feat/client-auth
mkdir -p docs/superpowers/plans
cp /home/yerza/.claude/plans/ticklish-dazzling-alpaca.md \
   docs/superpowers/plans/2026-09-19-klientskaya-chast-auth.md
git add docs/superpowers/plans/2026-09-19-klientskaya-chast-auth.md
git commit -m "docs: план клиентской части аутентификации"
```

---

## Структура файлов

**Создаются:**

| Файл | Ответственность |
|---|---|
| `backend/app/openapi.py` | выгрузка схемы: `python -m app.openapi > openapi.json` |
| `backend/tests/test_openapi_schema.py` | схема содержит пути этапа 1 и сериализуется |
| `frontend_client/src/shared/api/schema.d.ts` | **сгенерировано**, руками не править |
| `frontend_client/src/shared/api/client.ts` | `apiFetch`, `ApiError`, single-flight refresh |
| `frontend_client/src/shared/api/types.ts` | короткие алиасы поверх `schema.d.ts` |
| `frontend_client/src/shared/api/messages.ts` | `code` ошибки → текст для человека |
| `frontend_client/src/shared/ui/{Button,Input,Label,Field,Dialog,Spinner,Alert}.tsx` | примитивы на токенах |
| `frontend_client/src/shared/lib/cn.ts` | `clsx` + `tailwind-merge` |
| `frontend_client/src/app/{router.tsx,providers.tsx}` | `createRouter`, QueryClient, тема |
| `frontend_client/src/routes/*` | `__root`, `index`, `login`, `register`, `_authed`, `_authed.profile`, `_authed.tokens` |
| `frontend_client/src/features/auth/{api,model,components}/*` | сессия, формы входа и регистрации |
| `frontend_client/src/features/profile/{api,components}/*` | профиль и выход |
| `frontend_client/src/features/tokens/{api,components}/*` | список, выпуск и отзыв PAT |
| `frontend_client/src/test/{msw/,render.tsx}` | сервер MSW, обработчики, хелпер рендера |

**Изменяются:** `Makefile` (цель `api-types`), `.github/workflows/ci.yml` (джоба проверки
рассинхрона типов), `frontend_client/{package.json,vite.config.ts,eslint.config.js,.gitignore}`,
`frontend_client/src/{main.tsx,index.css}`, `frontend_client/src/app/App.tsx` (+ его тест),
`README.md`, `AGENTS.md`, спеки roadmap и architecture.

**Зависимости** (`cd frontend_client && bun add …`):
`@tanstack/react-router`, `@tanstack/react-query`, `react-hook-form`, `zod`,
`@hookform/resolvers`, `@radix-ui/react-dialog`, `@radix-ui/react-dropdown-menu`,
`class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`;
`bun add -d @tanstack/router-plugin msw openapi-typescript`.

---

### Task 1: Генерация типов из OpenAPI

**Files:** создать `backend/app/openapi.py`, `backend/tests/test_openapi_schema.py`;
изменить `Makefile`, `frontend_client/package.json`, `frontend_client/.gitignore`,
`.github/workflows/ci.yml`.

- [ ] **Шаг 1.** Тест `backend/tests/test_openapi_schema.py` (БД не нужна):

```python
def test_schema_covers_stage_one_paths() -> None:
    paths = json.loads(dump())["paths"]

    assert "/api/v1/auth/login" in paths
    assert "/api/v1/me" in paths
    assert "/api/v1/me/tokens" in paths
    assert "/api/v1/me/tokens/{token_id}" in paths


def test_dump_is_stable_and_readable() -> None:
    """Порядок ключей фиксирован: иначе каждая выгрузка даёт шумный diff."""
    first = dump()

    assert first == dump()
    assert first.endswith("\n")
    assert "\\u0410" not in first          # кириллица в описаниях остаётся читаемой
```

- [ ] **Шаг 2.** Запустить — падает на импорте.
- [ ] **Шаг 3.** `backend/app/openapi.py`: `def dump() -> str` =
      `json.dumps(create_app().openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"`;
      `main()` печатает результат в stdout. Приложение создаётся ради схемы, БД не трогается.
- [ ] **Шаг 4.** Цель в `Makefile`:

```make
api-types: ## Сгенерировать типы веб-клиента из OpenAPI
	uv run python -m app.openapi > $(FRONT)/openapi.json
	cd $(FRONT) && bun run generate:api
```

      В `package.json` — `"generate:api": "openapi-typescript openapi.json -o src/shared/api/schema.d.ts"`.
      `frontend_client/.gitignore` пополняется строкой `openapi.json` (промежуточный файл;
      в git лежит результат — `schema.d.ts`).
- [ ] **Шаг 5.** `make api-types`, прочитать `schema.d.ts` глазами: в нём должны быть
      `SessionResponse`, `MeResponse`, `TokenCreated`, `TokenList`.
- [ ] **Шаг 6.** В CI — джоба `api-types` с `uv` и `bun`, теми же `env`, что у `backend-tests`:
      `make api-types` и `git diff --exit-code frontend_client/src/shared/api/schema.d.ts`.
      Рассинхрон схемы и типов должен падать в CI, а не всплывать ошибкой компиляции у человека.
- [ ] **Шаг 7.** Коммит: `feat: генерация типов веб-клиента из OpenAPI`

---

### Task 2: Каркас клиента — роутер, Query, MSW

**Files:** `src/app/{providers.tsx,router.tsx}`, `src/routes/{__root.tsx,index.tsx}`,
`src/test/{msw/server.ts,msw/handlers.ts,render.tsx,setup.ts}`, `src/main.tsx`,
`vite.config.ts`, `eslint.config.js`, `src/app/App.tsx` + `App.test.tsx`.

**Produces:** приложение с типизированной файловой маршрутизацией и `QueryClientProvider`;
тестовый рендер, поднимающий память-роутер по заданному пути.

- [ ] **Шаг 1.** Поставить зависимости, подключить `@tanstack/router-plugin/vite` в `vite.config.ts`,
      добавить `src/routeTree.gen.ts` в `ignores` eslint.
- [ ] **Шаг 2.** Переписать `src/app/App.test.tsx`: старый тест проверяет статическую заглушку
      этапа 0, её больше нет. Новый:

```tsx
it('неаутентифицированного посетителя уводит на экран входа', async () => {
  server.use(unauthenticated())

  await renderApp({ path: '/' })

  expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument()
})
```

- [ ] **Шаг 3.** Запустить — падает.
- [ ] **Шаг 4.** Реализовать:
  - `providers.tsx` — `ThemeProvider` + `QueryClientProvider`. `QueryClient`:
    `retry: false` (повторять `401` и `422` бессмысленно), `refetchOnWindowFocus: true` (§4.5).
  - `router.tsx` — `createRouter({ routeTree, context: { queryClient } })` и модульная
    декларация `declare module '@tanstack/react-router'` для типобезопасного контекста.
  - `routes/__root.tsx` — `<Outlet/>` и страница 404.
  - `routes/index.tsx` — редирект на `/profile` (guard `_authed` сам уведёт на `/login`).
  - `src/test/render.tsx` — `renderApp({ path })`: свежий `QueryClient` на тест
    (`retry: false`, `gcTime: 0`), память-история, ожидание готовности роутера.
  - `src/test/msw/handlers.ts` — обработчики по умолчанию и фабрики
    `unauthenticated()`, `session(user)`, `failure(status, code)`.
  - `setup.ts` — `server.listen({ onUnhandledRequest: 'error' })`, `resetHandlers`, `close`.
- [ ] **Шаг 5.** Тесты зелёные, `lint`, `typecheck` чистые.
- [ ] **Шаг 6.** Коммит: `feat: маршрутизация, слой запросов и тестовый стенд веб-клиента`

---

### Task 3: http-клиент, ошибки и обновление сессии

**Files:** `src/shared/api/{client.ts,types.ts,messages.ts}`, `src/shared/api/client.test.ts`.

**Produces:**

```ts
class ApiError extends Error {
  status: number
  code: string          // из конверта {"error": {"code", …}}
  details: Record<string, unknown>
}

function apiFetch<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T>
function humanMessage(error: unknown): string
```

Правила, ради которых всё это существует:
- `credentials: 'include'` — иначе cookie не уезжает;
- `X-Requested-With: XMLHttpRequest` на каждом запросе: без него бэкенд отвечает `403 csrf_required`;
- ответ разбирается в `ApiError` по контракту §3.6; `204` возвращает `undefined`;
- `401` → один `POST /auth/refresh` и повтор исходного запроса. Параллельные запросы ждут **одно**
  обновление (single-flight). Сам `/auth/*` не рефрешится никогда, иначе получается петля.
  Неудачное обновление ставит флаг «сессии нет» и подавляет следующие попытки до успешного входа.

- [ ] **Шаг 1.** Тесты `client.test.ts` на MSW:

```ts
it('шлёт cookie и CSRF-заголовок', …)
it('разбирает конверт ошибки в ApiError с кодом', …)
it('обновляет сессию один раз на два параллельных 401 и повторяет оба запроса', …)
it('не пытается обновлять сессию для самого /auth/refresh', …)
it('после неудачного обновления не долбит /auth/refresh на каждый запрос', …)
it('возвращает undefined на 204', …)
it('переводит rate_limited в текст с секундами из details.retry_after', …)
```

- [ ] **Шаг 2.** Запустить — падает.
- [ ] **Шаг 3.** Реализовать. `messages.ts` — карта `code` → текст:
      `invalid_credentials` «Неверный email или пароль», `email_already_registered`
      «Этот email уже зарегистрирован», `rate_limited` «Слишком много попыток, подождите N с»,
      `token_reuse_detected` «Сессия закрыта из соображений безопасности, войдите заново»,
      `insufficient_scope` «Токену не хватает прав на изменение», иначе — `message` с сервера.
      `validation_error` разворачивается в ошибки полей по `details.errors[].loc`.
- [ ] **Шаг 4.** Тесты зелёные.
- [ ] **Шаг 5.** Коммит: `feat: http-клиент с единым разбором ошибок и обновлением сессии`

---

### Task 4: Сессия, защита маршрутов, оболочка

**Files:** `src/features/auth/api/session.ts`, `src/routes/_authed.tsx`,
`src/app/AppShell.tsx`, `src/features/auth/api/session.test.tsx`.

**Produces:** `sessionQueryOptions` (`queryKey: ['session']` → `GET /api/v1/me`),
хук `useSession()`, guard в `_authed.beforeLoad`.

- [ ] **Шаг 1.** Тесты:

```tsx
it('пускает аутентифицированного в /profile', …)
it('неаутентифицированного уводит на /login и запоминает, куда он шёл', …)   // ?redirect=/tokens
it('после входа возвращает на запомненный маршрут', …)
it('показывает в шапке имя пользователя и его роль инстанса', …)
it('токен со scope=read показан как режим только для чтения', …)             // scopes из /me
```

- [ ] **Шаг 2.** Запустить — падает.
- [ ] **Шаг 3.** Реализовать:
  - `_authed.beforeLoad` — `context.queryClient.ensureQueryData(sessionQueryOptions)`;
    `ApiError` со статусом `401` → `throw redirect({ to: '/login', search: { redirect: location.href } })`.
  - `AppShell` — шапка: название, имя пользователя, меню (Radix DropdownMenu) со ссылками
    «Профиль», «Токены доступа» и пунктом «Выйти», переключатель темы. Боковой навигации нет:
    вести из неё некуда до этапа 3.
  - `search`-схема `/login` (`redirect?: string`) — валидируется Zod, посторонний URL
    отбрасывается: открытый редирект по параметру недопустим.
- [ ] **Шаг 4.** Тесты зелёные.
- [ ] **Шаг 5.** Коммит: `feat: сессия, защита маршрутов и оболочка приложения`

---

### Task 5: Экран входа

**Files:** `src/routes/login.tsx`, `src/features/auth/{model/schemas.ts,components/LoginForm.tsx}`,
`src/shared/ui/*` (что понадобится: `Button`, `Input`, `Label`, `Field`, `Alert`),
`src/features/auth/components/LoginForm.test.tsx`.

- [ ] **Шаг 1.** Тесты:

```tsx
it('не отправляет форму с пустыми полями и показывает ошибки полей', …)
it('входит и переходит в приложение', …)
it('показывает «Неверный email или пароль» на 401', …)
it('показывает счётчик ожидания на 429', …)
it('блокирует кнопку на время запроса', …)
it('ведёт на регистрацию ссылкой', …)
```

- [ ] **Шаг 2.** Запустить — падает.
- [ ] **Шаг 3.** Реализовать: React Hook Form + `zodResolver`. Схема Zod повторяет ограничения
      бэкенда (email, пароль не пуст) — клиентская валидация экономит запрос, а не заменяет
      серверную. Мутация: `apiFetch('/api/v1/auth/login', …)` → `queryClient.setQueryData(['session'], …)`
      → `navigate({ to: search.redirect ?? '/profile' })`.
      Примитивы `shared/ui` пишутся здесь и переиспользуются дальше: `Button` на
      `class-variance-authority` с вариантами `primary | secondary | ghost | danger` и размерами,
      все цвета — токенами.
- [ ] **Шаг 4.** Тесты зелёные; проверить экран в обеих темах и на 360px.
- [ ] **Шаг 5.** Коммит: `feat: экран входа`

---

### Task 6: Экран регистрации

**Files:** `src/routes/register.tsx`, `src/features/auth/components/RegisterForm.tsx` + тест.

- [ ] **Шаг 1.** Тесты:

```tsx
it('требует пароль не короче восьми символов', …)          // то же ограничение, что в схеме бэкенда
it('регистрирует и сразу открывает приложение', …)          // регистрация логинит: cookie уже стоят
it('показывает «Этот email уже зарегистрирован» на 409', …)
it('раскладывает 422 по полям формы', …)                    // details.errors[].loc
```

- [ ] **Шаг 2.** Запустить — падает.
- [ ] **Шаг 3.** Реализовать. Поля: email, имя, пароль. Подтверждения пароля нет — поле видимого
      пароля с переключателем «показать» решает ту же задачу и не удваивает форму.
- [ ] **Шаг 4.** Тесты зелёные, обе темы, 360px.
- [ ] **Шаг 5.** Коммит: `feat: экран регистрации`

---

### Task 7: Профиль и выход

**Files:** `src/routes/_authed.profile.tsx`, `src/features/profile/*` + тесты.

- [ ] **Шаг 1.** Тесты:

```tsx
it('показывает email, имя и роль инстанса', …)
it('сохраняет новое имя и обновляет шапку', …)              // PATCH /me + setQueryData
it('показывает ошибку и возвращает прежнее значение при отказе', …)
it('переключает тему тремя состояниями: светлая, тёмная, системная', …)
it('выходит: гасит кэш и уводит на /login', …)
it('на PATCH под токеном со scope=read показывает, что изменение недоступно', …)
```

- [ ] **Шаг 2.** Запустить — падает.
- [ ] **Шаг 3.** Реализовать. Выход: `POST /auth/logout` → `queryClient.clear()` → `/login`.
      Трёхпозиционный переключатель темы (`light`/`dark`/`system`) живёт здесь — roadmap требует
      его именно в настройках профиля; существующий `ThemeToggle` в шапке остаётся быстрым
      переключением и использует тот же `useTheme`.
- [ ] **Шаг 4.** Тесты зелёные, обе темы, 360px.
- [ ] **Шаг 5.** Коммит: `feat: экран профиля и выход из сессии`

---

### Task 8: Страница токенов доступа

**Files:** `src/routes/_authed.tokens.tsx`, `src/features/tokens/*` + тесты,
`src/shared/ui/Dialog.tsx`.

- [ ] **Шаг 1.** Тесты:

```tsx
it('показывает пустое состояние, когда токенов нет', …)
it('перечисляет токены с префиксом, областью и датой последнего использования', …)
it('выпускает токен и показывает полное значение ровно один раз', …)
it('после закрытия окна полного значения на странице не остаётся', …)
it('копирует токен в буфер обмена', …)                      // navigator.clipboard замокан
it('отзывает токен после подтверждения и убирает его из списка', …)
it('не отзывает, если подтверждение отменено', …)
```

- [ ] **Шаг 2.** Запустить — падает.
- [ ] **Шаг 3.** Реализовать. Форма выпуска: имя, область (`read` / `read_write`) переключателем
      из двух кнопок-радио с пояснением, что именно даёт каждая, срок — необязательная дата.
      Полное значение показывается в модальном окне с кнопкой копирования и прямым
      предупреждением, что второй раз его не покажут: бэкенд хранит только хеш.
      Отзыв — через подтверждение с именем токена в тексте; `DELETE` отвечает `204`.
      Список инвалидируется ключом `['tokens']`.
- [ ] **Шаг 4.** Тесты зелёные, обе темы, 360px, обход страницы с клавиатуры.
- [ ] **Шаг 5.** Коммит: `feat: страница управления токенами доступа`

---

### Task 9: Закрытие среза

**Files:** `docs/superpowers/specs/2026-09-16-taskanline-roadmap.md`,
`…-architecture.md`, `AGENTS.md`, `README.md`.

- [ ] **Шаг 1.** Полная проверка: `make lint`, `make test`, `cd frontend_client && bun run build`.
      Вывод приложить в отчёт.
- [ ] **Шаг 2.** Ручной сценарий из раздела «Проверка» на живом бэкенде и чистой базе, с
      реальными наблюдениями (а не «должно работать»).
- [ ] **Шаг 3.** В roadmap, в этапе 5, отметить выполненные досрочно пункты и добавить строку о
      том, что они сделаны вместе с клиентской частью этапа 1; пункт «Экраны входа и регистрации»
      отметить частично — приём приглашения по ссылке появится на этапе 2 вместе с инвайтами.
- [ ] **Шаг 4.** Внести в спеки решения 2–5 из раздела Context (нет Zustand; shadcn руками;
      обновление сессии в http-клиенте; две команды генерации типов).
- [ ] **Шаг 5.** В `AGENTS.md` — раздел про клиент: где живёт http-клиент, почему
      `X-Requested-With` ставится централизованно, что `schema.d.ts` генерируется и правится
      только через `make api-types`. В `README.md` — как поднять клиент и бэкенд вместе.
- [ ] **Шаг 6.** Коммит: `docs: клиентская часть аутентификации, спеки и README обновлены`.
      В `dev` не вливать — слияние решает человек.

---

## Проверка

**Автоматическая**

```bash
make lint            # ruff, mypy, eslint, tsc
make test            # pytest + vitest
cd frontend_client && bun run build
```

**Ручная, на чистой базе**

```bash
make db-up && make migrate
make run                           # бэкенд на :8000
cd frontend_client && bun run dev  # клиент на :5173, /api проксируется на бэкенд
```

1. Открыть `http://localhost:5173/` → редирект на `/login`.
2. Перейти по ссылке на регистрацию, завести первого пользователя → попадание в приложение,
   в профиле роль инстанса `superadmin`.
3. Сменить имя в профиле → шапка обновилась без перезагрузки.
4. Выпустить токен со `scope = read`, скопировать значение, закрыть окно → в списке остался
   только префикс.
5. `curl -H "Authorization: Bearer <токен>" http://localhost:8000/api/v1/me` → профиль,
   `"auth_method": "token"`.
6. Отозвать токен в интерфейсе → тот же `curl` отвечает `401 invalid_token`.
7. Выйти → редирект на `/login`; попытка открыть `/tokens` уводит туда же с `?redirect=/tokens`,
   а вход возвращает на `/tokens`.
8. Переключить тему в профиле на светлую, перезагрузить страницу → мигания тёмным нет.
9. Сузить окно до 360px → ни один экран не даёт горизонтальной прокрутки.

Срез считается закрытым, когда шаги 1–9 проходят, `make test` и `make lint` зелёные, а
`bun run build` собирается.
