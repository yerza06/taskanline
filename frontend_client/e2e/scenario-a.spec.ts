import { expect, test } from '@playwright/test'

import { createProject, createTeam, createWorkspace, quickCreate, signUp, unique } from './helpers.ts'

/**
 * Сценарий А — запуск с нуля: регистрация, пространство, команда ENG, проект и
 * первая задача ENG-1. Ни одного шага через SQL или админку.
 */
test('с нуля до задачи ENG-1', async ({ page }) => {
  const slug = unique('a')
  await signUp(page, `${slug}@example.com`, 'Ольга Основатель')
  await createWorkspace(page, 'Стартап', slug)
  await createTeam(page, 'ENG', 'Инженерия')
  await createProject(page, 'Инженерия', 'Запуск')

  await expect(page.getByText('Задач нет')).toBeVisible()
  const key = await quickCreate(page, 'Первая задача')

  expect(key).toBe('ENG-1')
  await expect(page.getByRole('textbox', { name: 'Название задачи' })).toHaveValue('Первая задача')
  await expect(page.getByLabel('Проект')).toHaveValue(/.+/)
})
