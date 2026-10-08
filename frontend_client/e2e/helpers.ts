import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { expect, type Page } from '@playwright/test'

const SERVER_LOG = fileURLToPath(new URL('./.server.log', import.meta.url))
export const PASSWORD = 'correct horse battery staple'

/** Уникальная метка прогона: сценарии делят базу, адреса и slug не должны совпасть. */
export function unique(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`
}

export async function signUp(page: Page, email: string, name: string): Promise<void> {
  await page.goto('/register')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Имя').fill(name)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click()
}

export async function createWorkspace(page: Page, name: string, slug: string): Promise<void> {
  await expect(page.getByRole('heading', { name: 'Новое пространство' })).toBeVisible()
  await page.getByLabel('Название', { exact: true }).fill(name)
  await page.getByLabel('Адрес').fill(slug)
  await page.getByRole('button', { name: 'Создать пространство' }).click()
  await expect(page).toHaveURL(new RegExp(`/w/${slug}$`))
}

export async function createTeam(page: Page, key: string, name: string): Promise<void> {
  await page.getByRole('button', { name: 'Новая команда' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Название', { exact: true }).fill(name)
  await dialog.getByLabel('Ключ').fill(key)
  await dialog.getByRole('button', { name: 'Создать команду' }).click()
  await expect(page.getByRole('heading', { name })).toBeVisible()
  // Горячие клавиши молчат, пока открыто любое окно, — ждём, пока закроется.
  await expect(page.getByRole('dialog')).toHaveCount(0)
}

/** Создаёт проект в команде и возвращает его id — из адреса страницы проекта. */
export async function createProject(page: Page, teamName: string, name: string): Promise<string> {
  const team = page.getByRole('navigation').getByRole('listitem').filter({ hasText: teamName })
  await team.getByRole('button', { name: 'Проект' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Название', { exact: true }).fill(name)
  await dialog.getByRole('button', { name: 'Создать проект' }).click()
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  return page.url().split('/project/')[1] ?? ''
}

/** Быстрое создание: клавиша `c`, название, Enter. Возвращает ключ новой задачи. */
export async function quickCreate(page: Page, title: string): Promise<string> {
  const dialog = page.getByRole('dialog', { name: 'Новая задача' })
  // Страница могла ещё не дорисоваться — горячие клавиши появляются вместе с ней.
  await expect(page.getByRole('button', { name: 'Задача', exact: true })).toBeVisible()
  await expect(async () => {
    if (!(await dialog.isVisible())) await page.keyboard.press('c')
    await expect(dialog).toBeVisible({ timeout: 1000 })
  }).toPass()
  await dialog.getByLabel('Название', { exact: true }).fill(title)
  await dialog.getByLabel('Название', { exact: true }).press('Enter')
  await expect(page).toHaveURL(/\/task\/[A-Z]+-\d+$/)
  return page.url().split('/task/')[1] ?? ''
}

/**
 * Ссылка из письма-приглашения. Почта e2e-бэкенда пишется в его журнал
 * (`MAILER__BACKEND=console`), откуда её и берём — как человек взял бы из ящика.
 */
export async function invitationLink(email: string): Promise<string> {
  let found: string | undefined
  await expect
    .poll(() => {
      const lines = readFileSync(SERVER_LOG, 'utf-8').split('\n')
      for (const line of lines.reverse()) {
        if (line.includes('mail.console') && line.includes(email)) {
          found = /\/invite\/[A-Za-z0-9_-]+/.exec(line)?.[0]
          if (found) return found
        }
      }
      return undefined
    })
    .toBeTruthy()
  return found ?? ''
}
