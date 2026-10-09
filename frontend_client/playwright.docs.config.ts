import { defineConfig, devices } from '@playwright/test'

import base from './playwright.config.ts'

/**
 * Скриншоты для руководства пользователя (`docs/guide/images/`).
 *
 * Те же серверы, что у e2e: бэкенд на пересоздаваемой базе `taskanline_e2e` и порту
 * 8001, клиент на 5174, админка на 5176. Сценарий — файл `*.shots.ts`: обычный
 * `test:e2e` его не подхватывает, он ищет только `*.spec.ts`.
 */
export default defineConfig({
  ...base,
  testDir: './e2e/docs',
  testMatch: '*.shots.ts',
  retries: 0,
  reporter: 'list',
  timeout: 300_000,
  use: {
    ...base.use,
    ...devices['Desktop Chrome'],
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    locale: 'ru-RU',
    colorScheme: 'light',
  },
  projects: undefined,
})
