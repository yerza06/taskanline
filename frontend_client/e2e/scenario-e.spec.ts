import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'

import { PASSWORD, quickCreate, signUp, unique, createTeam, createWorkspace } from './helpers.ts'

const ADMIN = 'http://localhost:5176'
const REPO = fileURLToPath(new URL('../..', import.meta.url))
const XHR = { 'X-Requested-With': 'XMLHttpRequest' }

/** Роль инстанса — серверной командой, как и при восстановлении доступа на живом сервере. */
function grantSuperadmin(email: string): void {
  execFileSync('uv', ['run', 'python', '-m', 'app.admin', 'grant', '--email', email, '--role', 'superadmin'], {
    cwd: REPO,
    env: { ...process.env, DB__NAME: 'taskanline_e2e' },
    stdio: 'ignore',
  })
}

/**
 * Сценарий Е: владелец инстанса блокирует уволившегося — у того немедленно
 * перестают работать и сессия, и токен агента; затем закрывает регистрацию. Оба
 * действия — в журнале с актором и адресом, а текста задач админка не показывает.
 */
test('блокировка, закрытие регистрации, журнал', async ({ page, browser }) => {
  const tag = unique('e')
  const rootEmail = `${tag}-root@example.com`
  const leaverEmail = `${tag}-leaver@example.com`

  // Уволившийся работал: пространство, задача, токен агента.
  const leaverContext = await browser.newContext()
  const leaver = await leaverContext.newPage()
  await signUp(leaver, leaverEmail, 'Пётр Уходящий')
  await createWorkspace(leaver, 'Старая работа', tag)
  await createTeam(leaver, 'ENG', 'Инженерия')
  await quickCreate(leaver, 'СЕКРЕТНАЯ-ЗАДАЧА')
  const issued = await leaver.request.post('/api/v1/me/tokens', {
    headers: XHR,
    data: { name: 'agent', scope: 'read_write' },
  })
  const agentToken = ((await issued.json()) as { token: string }).token

  await signUp(page, rootEmail, 'Ольга Владелец')
  grantSuperadmin(rootEmail)

  // Админка открывается той же сессией и пишет вход в журнал.
  await page.goto(ADMIN)
  await expect(page.getByRole('heading', { name: 'Обзор' })).toBeVisible()
  await page.getByRole('link', { name: 'Пользователи' }).click()
  await page.getByLabel('Поиск по email и имени').fill(leaverEmail)
  await page.getByRole('link', { name: leaverEmail }).click()
  await page.getByRole('button', { name: 'Заблокировать' }).click()
  await expect(page.getByRole('status')).toContainText('сессии и токены отозваны')

  // У заблокированного не работает ни вкладка, ни агент.
  expect((await leaver.request.get('/api/v1/me')).status()).toBe(401)
  await leaver.goto('/')
  await expect(leaver).toHaveURL(/\/login/)
  const agent = await leaverContext.request.get('http://127.0.0.1:8001/api/v1/me', {
    headers: { Authorization: `Bearer ${agentToken}` },
  })
  expect(agent.status()).toBe(401)

  // Регистрация — только по приглашению; подтверждение паролем.
  await page.getByRole('link', { name: 'Настройки' }).click()
  await page.getByLabel('Регистрация').selectOption('invite_only')
  await page.getByRole('button', { name: 'Сохранить' }).click()
  const reauth = page.getByRole('dialog', { name: 'Подтвердите паролем' })
  await reauth.getByLabel('Пароль').fill(PASSWORD)
  await reauth.getByRole('button', { name: 'Подтвердить' }).click()
  await expect(page.getByText('Сохранено.')).toBeVisible()

  const stranger = await (await browser.newContext()).newPage()
  await signUp(stranger, `${tag}-stranger@example.com`, 'Чужой')
  await expect(stranger.getByRole('alert')).toContainText('только по приглашению')

  // Оба действия — в журнале, с актором и адресом.
  await page.getByRole('link', { name: 'Журнал' }).click()
  const blocked = page.getByRole('listitem').filter({ hasText: 'Пользователь заблокирован' }).first()
  await expect(blocked).toContainText(rootEmail)
  await expect(blocked).toContainText(/127\.0\.0\.1|::1/)
  await expect(page.getByRole('listitem').filter({ hasText: 'Изменены настройки инстанса' }).first()).toContainText(
    rootEmail,
  )

  // Ни один экран админки не показывает текст задач.
  for (const path of ['/', '/users', '/workspaces', '/audit', '/settings']) {
    await page.goto(`${ADMIN}${path}`)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByText('СЕКРЕТНАЯ-ЗАДАЧА')).toHaveCount(0)
  }

  // PAT в админке не работает ни при какой роли; обычному человеку раздела нет.
  const rootToken = (
    (await (
      await page.request.post('/api/v1/me/tokens', {
        headers: XHR,
        data: { name: 'root-agent', scope: 'read_write' },
      })
    ).json()) as { token: string }
  ).token
  const patAdmin = await page.request.get('http://127.0.0.1:8001/api/v1/admin/users', {
    headers: { Authorization: `Bearer ${rootToken}` },
  })
  expect(patAdmin.status()).toBe(403)
  expect(((await patAdmin.json()) as { error: { code: string } }).error.code).toBe('session_required')

  // Регистрация нужна остальным сценариям прогона — возвращаем как было.
  const reopened = await page.request.patch('/api/v1/admin/settings', {
    headers: XHR,
    data: { registration_mode: 'open' },
  })
  expect(reopened.status()).toBe(200)
})

test('обычному пользователю админка — «страница не найдена»', async ({ page }) => {
  await signUp(page, `${unique('u')}@example.com`, 'Обычный')
  await expect(page.getByRole('heading', { name: 'Новое пространство' })).toBeVisible()
  await page.goto(ADMIN)
  await expect(page.getByText('Страница не найдена')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Разделы' })).toHaveCount(0)
})
