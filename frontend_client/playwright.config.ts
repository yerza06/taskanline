import { defineConfig, devices } from '@playwright/test'

/**
 * Сценарии А–В и Е из видения — против настоящего бэкенда.
 *
 * Бэкенд поднимается на своей базе `taskanline_e2e` (пересоздаётся перед прогоном)
 * и порту 8001, клиент — Vite на 5174 с прокси на него: обычной разработке на
 * 8000/5173 прогон не мешает. Сценарии делят базу, поэтому идут по одному.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 60_000,
  use: {
    baseURL: 'http://localhost:5174',
    trace: 'retain-on-failure',
    locale: 'ru-RU',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'bash e2e/backend.sh',
      url: 'http://127.0.0.1:8001/health',
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: 'ignore',
    },
    {
      command: 'bunx vite --port 5174 --strictPort',
      url: 'http://localhost:5174',
      timeout: 60_000,
      reuseExistingServer: false,
      env: { API_TARGET: 'http://127.0.0.1:8001' },
    },
    {
      // Админ-панель на своём порту того же хоста: cookie сессии общие с клиентом.
      command: 'bunx vite --port 5176 --strictPort',
      cwd: '../frontend_admin',
      url: 'http://localhost:5176',
      timeout: 60_000,
      reuseExistingServer: false,
      env: { API_TARGET: 'http://127.0.0.1:8001', VITE_CLIENT_URL: 'http://localhost:5174' },
    },
  ],
})
