import { execFileSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { expect, request, test, type APIRequestContext, type Page } from '@playwright/test'

import { PASSWORD, createWorkspace, invitationLink, signUp } from '../helpers.ts'

/**
 * Скриншоты для `docs/guide/`. Не проверка, а съёмка: сценарий заселяет пустую
 * базу e2e правдоподобной командой (люди, команды, проекты, задачи, обсуждения,
 * views) и фотографирует экраны клиента и админки.
 *
 * Запуск: `make docs-screenshots` (или `bun run docs:screenshots`), нужен `make db-up`.
 */

const CLIENT = 'http://localhost:5174'
const ADMIN = 'http://localhost:5176'
const REPO = fileURLToPath(new URL('../../..', import.meta.url))
const IMAGES = fileURLToPath(new URL('../../../docs/guide/images/', import.meta.url))
const XHR = { 'X-Requested-With': 'XMLHttpRequest' }

const OWNER = { email: 'anna@acme.example', name: 'Анна Смирнова' }
const PEOPLE = [
  { email: 'boris@acme.example', name: 'Борис Петров', key: 'boris' },
  { email: 'vera@acme.example', name: 'Вера Ким', key: 'vera' },
  { email: 'dmitry@partner.example', name: 'Дмитрий Орлов', key: 'dmitry' },
] as const

type Person = (typeof PEOPLE)[number]['key'] | 'anna'
type Json = Record<string, unknown>

async function shot(page: Page, name: string): Promise<void> {
  // Даём дорисоваться шрифтам и анимациям окон Radix.
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${IMAGES}${name}.png` })
}

async function call(api: APIRequestContext, method: string, path: string, data?: unknown, headers = {}) {
  const response = await api.fetch(`${CLIENT}/api/v1${path}`, {
    method,
    headers: { ...XHR, ...headers },
    data,
  })
  if (!response.ok()) throw new Error(`${method} ${path}: ${response.status()} ${await response.text()}`)
  return response.status() === 204 ? {} : ((await response.json()) as Json)
}

function grantSuperadmin(email: string): void {
  execFileSync('uv', ['run', 'python', '-m', 'app.admin', 'grant', '--email', email, '--role', 'superadmin'], {
    cwd: REPO,
    env: { ...process.env, DB__NAME: 'taskanline_e2e' },
    stdio: 'ignore',
  })
}

test('скриншоты руководства', async ({ page, browser }) => {
  mkdirSync(IMAGES, { recursive: true })

  // --- Вход и регистрация --------------------------------------------------------
  await page.goto('/login')
  await expect(page.getByRole('button', { name: 'Войти' })).toBeVisible()
  await shot(page, 'login')
  await page.goto('/register')
  await page.getByLabel('Email').fill(OWNER.email)
  await page.getByLabel('Имя').fill(OWNER.name)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await shot(page, 'register')

  await signUp(page, OWNER.email, OWNER.name)
  grantSuperadmin(OWNER.email)
  await expect(page.getByRole('heading', { name: 'Новое пространство' })).toBeVisible()
  await page.getByLabel('Название', { exact: true }).fill('Acme')
  await page.getByLabel('Адрес').fill('acme')
  await shot(page, 'onboarding')
  await page.getByLabel('Название', { exact: true }).clear()
  await createWorkspace(page, 'Acme', 'acme')

  // --- Данные: через API, от имени владельца --------------------------------------
  const owner = page.request
  const ws = await call(owner, 'GET', '/workspaces').then((body) => (body.items as Json[])[0])
  const wsId = ws.id as string
  const eng = await call(owner, 'POST', `/workspaces/${wsId}/teams`, {
    key: 'ENG',
    name: 'Инженерия',
    description: 'Бэкенд, мобильное приложение и инфраструктура',
  })
  const des = await call(owner, 'POST', `/workspaces/${wsId}/teams`, {
    key: 'DES',
    name: 'Дизайн',
    description: 'Интерфейсы, сайт и бренд',
  })

  const mobile = await call(owner, 'POST', `/teams/${eng.id as string}/projects`, {
    name: 'Мобильное приложение',
    description: 'Версия 2.0 для iOS и Android',
    status: 'in_progress',
  })
  const payments = await call(owner, 'POST', `/teams/${eng.id as string}/projects`, {
    name: 'Платёжный шлюз',
    status: 'planned',
  })
  const site = await call(owner, 'POST', `/teams/${des.id as string}/projects`, {
    name: 'Редизайн сайта',
    status: 'in_progress',
  })

  // Люди приходят по приглашениям — как и в жизни.
  const sessions: Record<Person, APIRequestContext> = { anna: owner } as Record<Person, APIRequestContext>
  const invites: [Person, string, string, string][] = [
    ['boris', 'team', eng.id as string, 'member'],
    ['vera', 'team', des.id as string, 'lead'],
    ['dmitry', 'project', mobile.id as string, 'member'],
  ]
  const ids = {} as Record<Person, string>
  ids.anna = (await call(owner, 'GET', '/me')).id as string
  for (const [key, scopeType, scopeId, role] of invites) {
    const person = PEOPLE.find((p) => p.key === key)!
    await call(owner, 'POST', '/invitations', { email: person.email, scope_type: scopeType, scope_id: scopeId, role })
    const token = (await invitationLink(person.email)).split('/invite/')[1]
    const context = await request.newContext()
    await call(context, 'POST', `/invitations/token/${token}/accept`, { full_name: person.name, password: PASSWORD })
    sessions[key] = context
    ids[key] = (await call(context, 'GET', '/me')).id as string
  }

  // Приглашённый в команду приходит гостем пространства; своих сотрудников владелец
  // делает участниками (видят все открытые команды), а подрядчик остаётся гостем.
  await call(owner, 'PATCH', `/workspaces/${wsId}/members/${ids.boris}`, { role: 'member' })
  await call(owner, 'PATCH', `/workspaces/${wsId}/members/${ids.vera}`, { role: 'admin' })

  const states = async (team: Json) =>
    Object.fromEntries(
      ((await call(owner, 'GET', `/teams/${team.id as string}/states`)).items as Json[]).map((s) => [
        s.name as string,
        s.id as string,
      ]),
    )
  const engStates = await states(eng)
  const desStates = await states(des)

  const label = (name: string, color: string, team?: Json) =>
    call(owner, 'POST', '/labels', { workspace_id: wsId, team_id: team?.id ?? null, name, color })
  const bug = await label('bug', '#111111')
  const feature = await label('feature', '#555555')
  const backend = await label('backend', '#888888', eng)
  const ux = await label('ux', '#aaaaaa', des)

  let n = 0
  const task = async (who: Person, fields: Json) =>
    call(sessions[who], 'POST', '/tasks', fields, { 'Idempotency-Key': `docs-${++n}` })

  type Spec = [string, Json | null, string, number, Person | null, Json[], string?]
  const engTasks: Spec[] = [
    ['Вход через Apple ID падает на iOS 18', mobile, 'In Progress', 1, 'anna', [bug], '2026-10-14'],
    ['Офлайн-режим для списка заказов', mobile, 'Todo', 2, 'boris', [feature]],
    ['Push-уведомления о смене статуса', mobile, 'In Progress', 2, 'boris', [feature, backend]],
    ['Экран оплаты съезжает на маленьких экранах', mobile, 'Todo', 2, 'dmitry', [bug]],
    ['Подготовить сборку 2.0 в TestFlight', mobile, 'Backlog', 3, 'anna', []],
    ['Интеграция с эквайрингом банка', payments, 'Backlog', 2, 'boris', [backend, feature], '2026-11-01'],
    ['Повторная отправка вебхуков при сбое', payments, 'Todo', 3, null, [backend]],
    ['Таймаут БД при выгрузке отчёта', null, 'In Progress', 1, 'anna', [bug, backend]],
    ['Обновить зависимости до Python 3.13', null, 'Done', 4, 'boris', [backend]],
    ['Дублируются письма-приглашения', null, 'Done', 2, 'anna', [bug]],
    ['Ротация ключей шифрования', null, 'Backlog', 0, null, [backend]],
  ]
  const created: Record<string, Json> = {}
  for (const [title, project, state, priority, assignee, labels, due] of engTasks) {
    created[title] = await task('anna', {
      title,
      team_id: eng.id,
      project_id: project ? project.id : undefined,
      state_id: engStates[state],
      priority,
      assignee_id: assignee ? ids[assignee] : undefined,
      label_ids: labels.map((l) => l.id),
      due_date: due,
    })
  }
  const desTasks: Spec[] = [
    ['Новая главная страница', site, 'In Progress', 2, 'vera', [ux]],
    ['Иконки для раздела тарифов', site, 'Todo', 3, 'vera', [ux]],
    ['Аудит доступности форм', site, 'Backlog', 3, 'anna', [ux]],
  ]
  for (const [title, project, state, priority, assignee, labels] of desTasks) {
    await task('vera', {
      title,
      team_id: des.id,
      project_id: project?.id,
      state_id: desStates[state],
      priority,
      assignee_id: assignee ? ids[assignee] : undefined,
      label_ids: labels.map((l) => l.id),
    })
  }

  // Главная задача руководства — с описанием, подзадачами, связью и обсуждением.
  const main = created['Вход через Apple ID падает на iOS 18']
  const mainKey = main.key as string
  await call(owner, 'PATCH', `/tasks/${mainKey}`, {
    description: [
      'После обновления до iOS 18 вход через Apple ID завершается ошибкой `invalid_grant`.',
      '',
      '**Шаги:**',
      '1. Установить сборку 1.9.4 на iPhone с iOS 18.',
      '2. Нажать «Войти через Apple».',
      '3. Подтвердить Face ID.',
      '',
      '**Ожидаемо:** открывается список заказов.',
      '**На деле:** «Не удалось войти», в логах `invalid_grant`.',
    ].join('\n'),
  })
  for (const title of ['Воспроизвести на тестовом устройстве', 'Обновить SDK Sign in with Apple']) {
    await task('anna', { title, team_id: eng.id, project_id: mobile.id, parent_id: mainKey, state_id: engStates.Todo })
  }
  await call(owner, 'POST', `/tasks/${mainKey}/relations`, {
    type: 'blocks',
    target_id: created['Подготовить сборку 2.0 в TestFlight'].key,
  })
  await call(sessions.boris, 'POST', `/tasks/${mainKey}/comments`, {
    body: 'Воспроизвёл на iPhone 15: падает только при первом входе, повторный проходит.',
  })
  await call(sessions.dmitry, 'POST', `/tasks/${mainKey}/comments`, {
    body: 'Похоже на смену `redirect_uri` в консоли Apple — проверю настройки и отпишусь.',
  })
  await call(owner, 'POST', `/tasks/${mainKey}/comments`, {
    body: 'Спасибо! Если подтвердится — выпускаем 1.9.5 вне очереди.',
  })
  // Что-нибудь во «Входящих» владельца: Борис назначает и комментирует.
  await call(sessions.boris, 'PATCH', `/tasks/${created['Ротация ключей шифрования'].key as string}`, {
    assignee_id: ids.anna,
  })
  await call(sessions.boris, 'POST', `/tasks/${created['Таймаут БД при выгрузке отчёта'].key as string}/comments`, {
    body: 'Добавил индекс на `orders.created_at`, на стенде выгрузка за 3 секунды.',
  })
  await call(sessions.boris, 'PATCH', `/tasks/${created['Таймаут БД при выгрузке отчёта'].key as string}`, {
    state_id: engStates.Done,
  })

  // Сохранённые views: личный, командный и общий.
  const bugsView = await call(owner, 'POST', '/views', {
    workspace_id: wsId,
    scope: 'team',
    team_id: eng.id,
    name: 'Незакрытые баги',
    filters: {
      label_id: { op: 'in', value: [bug.id] },
      state_type: { op: 'nin', value: ['completed', 'canceled'] },
    },
    group_by: 'priority',
    layout: 'board',
  })
  await call(owner, 'POST', '/views', {
    workspace_id: wsId,
    scope: 'workspace',
    name: 'Срочное по всем командам',
    filters: { priority: { op: 'in', value: [1, 2] }, state_type: { op: 'nin', value: ['completed', 'canceled'] } },
    sort_by: 'priority',
  })
  await call(owner, 'POST', '/views', {
    workspace_id: wsId,
    scope: 'user',
    name: 'Мои на этой неделе',
    filters: { assignee_id: { op: 'in', value: ['@me'] } },
  })

  // --- Веб-клиент ----------------------------------------------------------------
  const w = '/w/acme'
  await page.goto(w)
  await expect(page.getByRole('navigation').getByText('Инженерия')).toBeVisible()
  await shot(page, 'workspace')

  await page.goto(`${w}/team/ENG`)
  await expect(page.getByRole('link', { name: 'Офлайн-режим для списка заказов' })).toBeVisible()
  await shot(page, 'team-list')

  await page.setViewportSize({ width: 1680, height: 900 })
  await page.goto(`${w}/team/ENG?layout=board`)
  await expect(page.getByRole('main').getByRole('region', { name: 'In Progress' })).toBeVisible()
  await shot(page, 'team-board')
  await page.setViewportSize({ width: 1440, height: 900 })

  await page.goto(`${w}/project/${mobile.id as string}`)
  await expect(page.getByRole('heading', { name: 'Мобильное приложение', level: 1 })).toBeVisible()
  await shot(page, 'project')

  await page.goto(`${w}/task/${mainKey}`)
  await expect(page.getByRole('textbox', { name: 'Название задачи' })).toHaveValue(main.title as string)
  await expect(page.getByText('Спасибо! Если подтвердится')).toBeVisible()
  await shot(page, 'task')

  await page.goto(`${w}/team/ENG`)
  await page.getByRole('button', { name: 'Фильтры' }).click()
  const filters = page.getByRole('group', { name: 'Фильтры' })
  for (const field of ['Метка', 'Тип статуса']) {
    await filters.getByRole('button', { name: 'Условие', exact: true }).click()
    await page.getByRole('menuitem', { name: field }).click()
  }
  await filters.getByRole('button', { name: 'Выберите…' }).first().click()
  await page.getByRole('menuitemcheckbox', { name: 'bug' }).click()
  await page.keyboard.press('Escape')
  await filters.getByLabel('Условие: Тип статуса', { exact: true }).selectOption('nin')
  await filters.getByRole('button', { name: 'Выберите…' }).click()
  await page.getByRole('menuitemcheckbox', { name: 'Завершена' }).click()
  await page.keyboard.press('Escape')
  await shot(page, 'filters')
  await page.getByRole('button', { name: 'Сохранить как view' }).click()
  await page.getByRole('dialog').getByLabel('Название', { exact: true }).fill('Мои баги')
  await shot(page, 'view-save')
  await page.keyboard.press('Escape')

  await page.goto(`${w}/view/${bugsView.id as string}`)
  await expect(page.getByRole('heading', { name: 'Незакрытые баги' })).toBeVisible()
  await shot(page, 'view')

  await page.goto(`${w}/team/ENG`)
  await expect(page.getByRole('button', { name: 'Задача', exact: true })).toBeVisible()
  await page.keyboard.press('c')
  const quick = page.getByRole('dialog', { name: 'Новая задача' })
  await expect(quick).toBeVisible()
  await quick.getByLabel('Название', { exact: true }).fill('Кэшировать аватары в приложении')
  await shot(page, 'quick-create')
  await page.keyboard.press('Escape')
  await expect(quick).toHaveCount(0)
  await page.keyboard.press('?')
  await expect(page.getByRole('dialog')).toBeVisible()
  await shot(page, 'hotkeys')
  await page.keyboard.press('Escape')

  await page.goto(`${w}/inbox`)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await shot(page, 'inbox')

  await page.goto(`${w}/members`)
  await expect(page.getByText(PEOPLE[0].email)).toBeVisible()
  await shot(page, 'members')

  await page.goto(`${w}/project/${mobile.id as string}`)
  await page.getByRole('button', { name: 'Участники' }).click()
  await page.getByRole('dialog').getByLabel('Email приглашённого').fill('olga@partner.example')
  await shot(page, 'invite')
  await page.keyboard.press('Escape')

  await page.goto(`${w}/team/ENG/settings`)
  await expect(page.getByRole('region', { name: 'Участники команды' })).toBeVisible()
  // Статусы, метки и участники целиком — страница длиннее экрана.
  await page.screenshot({ path: `${IMAGES}team-settings.png`, fullPage: true })

  await page.goto('/profile')
  await expect(page.getByRole('heading', { name: 'Профиль' })).toBeVisible()
  await shot(page, 'profile')

  await page.goto('/tokens')
  await page.getByLabel('Название').fill('claude-code')
  await page.getByRole('radio', { name: /Чтение и запись/ }).check()
  await page.getByRole('button', { name: 'Выпустить токен' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await shot(page, 'token-created')
  await page.getByRole('dialog').getByRole('button').last().click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await shot(page, 'tokens')

  // Приглашение глазами получателя — страница по ссылке из письма.
  await call(owner, 'POST', '/invitations', {
    email: 'olga@partner.example',
    scope_type: 'team',
    scope_id: des.id,
    role: 'member',
  })
  const guest = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
  await guest.goto(`${CLIENT}${await invitationLink('olga@partner.example')}`)
  await expect(guest.getByRole('button', { name: 'Создать учётную запись и принять' })).toBeVisible()
  await shot(guest, 'invite-accept')

  // Тёмная тема — по системной настройке.
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.setViewportSize({ width: 1680, height: 900 })
  await page.goto(`${w}/team/ENG?layout=board`)
  await expect(page.getByRole('main').getByRole('region', { name: 'In Progress' })).toBeVisible()
  await shot(page, 'dark-board')
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(`${w}/task/${mainKey}`)
  await expect(page.getByText('Спасибо! Если подтвердится')).toBeVisible()
  await shot(page, 'dark-task')
  await page.emulateMedia({ colorScheme: 'light' })

  // --- Админ-панель --------------------------------------------------------------
  await page.goto(ADMIN)
  await expect(page.getByRole('heading', { name: 'Обзор' })).toBeVisible()
  await shot(page, 'admin-overview')

  await page.getByRole('link', { name: 'Пользователи' }).click()
  await expect(page.getByRole('link', { name: PEOPLE[0].email })).toBeVisible()
  await shot(page, 'admin-users')
  await page.getByRole('link', { name: PEOPLE[0].email }).click()
  await expect(page.getByRole('button', { name: 'Заблокировать' })).toBeVisible()
  await shot(page, 'admin-user')
  await page.getByRole('button', { name: 'Отправить ссылку на смену пароля' }).click()
  await expect(page.getByRole('status')).toBeVisible()

  await page.goto(`${ADMIN}/workspaces`)
  await expect(page.getByRole('link', { name: /Acme/ })).toBeVisible()
  await shot(page, 'admin-workspaces')
  await page.getByRole('link', { name: /Acme/ }).first().click()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await shot(page, 'admin-workspace')

  await page.goto(`${ADMIN}/settings`)
  await page.getByLabel('Регистрация').selectOption('invite_only')
  await shot(page, 'admin-settings')
  await page.getByRole('button', { name: 'Сохранить' }).click()
  const reauth = page.getByRole('dialog', { name: 'Подтвердите паролем' })
  await expect(reauth).toBeVisible()
  await shot(page, 'admin-reauth')
  await reauth.getByLabel('Пароль').fill(PASSWORD)
  await reauth.getByRole('button', { name: 'Подтвердить' }).click()
  await expect(page.getByText('Сохранено.')).toBeVisible()

  await page.goto(`${ADMIN}/audit`)
  await expect(page.getByRole('listitem').filter({ hasText: 'Изменены настройки инстанса' }).first()).toBeVisible()
  await shot(page, 'admin-audit')
})
