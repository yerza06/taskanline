import { expect, test } from '@playwright/test'

import {
  PASSWORD,
  createProject,
  createTeam,
  createWorkspace,
  invitationLink,
  quickCreate,
  signUp,
  unique,
} from './helpers.ts'

/**
 * Сценарий Б — подрядчик: приглашён в один проект, видит его задачи и не видит ни
 * одной чужой. Прямая ссылка на чужую задачу — «не найдена», а не «нет доступа».
 */
test('подрядчик видит только свой проект', async ({ page, browser }) => {
  const slug = unique('b')
  const contractorEmail = `${slug}-contractor@example.com`
  await signUp(page, `${slug}@example.com`, 'Ольга Владелец')
  await createWorkspace(page, 'Агентство', slug)
  await createTeam(page, 'ENG', 'Инженерия')
  const projectId = await createProject(page, 'Инженерия', 'Сайт клиента')
  const inProject = await quickCreate(page, 'Свёрстать главную')

  await page.goto(`/w/${slug}/team/ENG`)
  const outside = await quickCreate(page, 'Внутренняя задача')

  await page.goto(`/w/${slug}/project/${projectId}`)
  await page.getByRole('button', { name: 'Участники' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Email приглашённого').fill(contractorEmail)
  await dialog.getByRole('button', { name: 'Пригласить' }).click()
  await expect(dialog.getByRole('status')).toContainText(contractorEmail)

  const contractor = await (await browser.newContext()).newPage()
  await contractor.goto(await invitationLink(contractorEmail))
  await contractor.getByLabel('Имя').fill('Пётр Подрядчик')
  await contractor.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await contractor.getByRole('button', { name: 'Создать учётную запись и принять' }).click()
  await expect(contractor).toHaveURL(new RegExp(`/w/${slug}`))

  await contractor.goto(`/w/${slug}/project/${projectId}`)
  await expect(contractor.getByRole('link', { name: 'Свёрстать главную' })).toBeVisible()
  await expect(contractor.getByText('Внутренняя задача')).toHaveCount(0)

  await contractor.goto(`/w/${slug}/task/${inProject}`)
  await expect(contractor.getByRole('textbox', { name: 'Название задачи' })).toHaveValue(
    'Свёрстать главную',
  )
  await contractor.goto(`/w/${slug}/task/${outside}`)
  await expect(contractor.getByText(`Задача ${outside} не найдена или недоступна.`)).toBeVisible()
})
