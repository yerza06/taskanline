import { expect, test, type Page } from '@playwright/test'

import {
  PASSWORD,
  createTeam,
  createWorkspace,
  invitationLink,
  quickCreate,
  signUp,
  unique,
} from './helpers.ts'

async function addLabel(page: Page, slug: string, name: string): Promise<void> {
  await page.goto(`/w/${slug}/team/ENG/settings`)
  await page.getByLabel('Название метки').fill(name)
  await page.getByRole('button', { name: 'Добавить метку' }).click()
  await expect(page.getByRole('button', { name: `Удалить метку ${name}` })).toBeVisible()
}

async function bug(page: Page, slug: string, title: string, priority: string, mine: boolean): Promise<void> {
  await page.goto(`/w/${slug}/team/ENG`)
  await quickCreate(page, title)
  await page.getByLabel('Приоритет', { exact: true }).selectOption({ label: priority })
  if (mine) await page.getByLabel('Исполнитель', { exact: true }).selectOption({ label: 'Вера Лид' })
  await page.getByRole('group', { name: 'Метки' }).getByText('bug').click()
  await expect(page.getByRole('group', { name: 'Метки' }).getByRole('checkbox', { name: 'bug' })).toBeChecked()
}

/**
 * Сценарий В — Views: «Мои незакрытые баги» — исполнитель я, метка bug, статус не
 * завершён, группировка по приоритету, доска. Сохраняется для команды, открывается
 * из бокового меню одним щелчком, и его видит другой участник команды.
 */
test('view «Мои незакрытые баги»', async ({ page, browser }) => {
  const slug = unique('c')
  const peerEmail = `${slug}-peer@example.com`
  await signUp(page, `${slug}@example.com`, 'Вера Лид')
  await createWorkspace(page, 'Продукт', slug)
  await createTeam(page, 'ENG', 'Инженерия')
  await addLabel(page, slug, 'bug')
  await bug(page, slug, 'Падает вход', 'Срочный', true)
  await bug(page, slug, 'Съехала кнопка', 'Низкий', true)
  await bug(page, slug, 'Чужой баг', 'Высокий', false)

  await page.goto(`/w/${slug}/team/ENG?layout=board`)
  await page.getByRole('button', { name: 'Фильтры' }).click()
  const filters = page.getByRole('group', { name: 'Фильтры' })
  for (const field of ['Исполнитель', 'Метка', 'Тип статуса']) {
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
  await page.getByLabel('Группировка').selectOption('priority')

  await page.getByRole('button', { name: 'Сохранить как view' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Название', { exact: true }).fill('Мои незакрытые баги')
  await dialog.getByLabel('Кому виден').selectOption('team')
  await dialog.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page).toHaveURL(/\/view\//)

  const board = page.getByRole('main')
  await expect(board.getByRole('region', { name: 'Срочный' })).toContainText('Падает вход')
  await expect(board.getByRole('region', { name: 'Низкий' })).toContainText('Съехала кнопка')
  await expect(board.getByText('Чужой баг')).toHaveCount(0)

  // Участник команды видит командный view в меню и открывает его одним щелчком.
  await page.goto(`/w/${slug}/team/ENG/settings`)
  const members = page.getByRole('region', { name: 'Участники команды' })
  await members.getByLabel('Email приглашённого').fill(peerEmail)
  await members.getByRole('button', { name: 'Пригласить' }).click()
  await expect(members.getByRole('status')).toContainText(peerEmail)

  const peer = await (await browser.newContext()).newPage()
  await peer.goto(await invitationLink(peerEmail))
  await peer.getByLabel('Имя').fill('Кирилл Коллега')
  await peer.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await peer.getByRole('button', { name: 'Создать учётную запись и принять' }).click()
  await expect(peer).toHaveURL(new RegExp(`/w/${slug}`))
  await peer.getByRole('navigation').getByRole('link', { name: 'Мои незакрытые баги' }).click()
  await expect(peer.getByRole('heading', { name: 'Мои незакрытые баги' })).toBeVisible()
  // `@me` — свой у каждого: на коллегу баги не назначены.
  await expect(peer.getByText('Падает вход')).toHaveCount(0)
})
