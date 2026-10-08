import { fileURLToPath } from 'node:url'

import { tanstackRouter } from '@tanstack/router-plugin/vite'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [
    // Плагин собирает src/routes/* в типизированное дерево маршрутов
    // (src/routeTree.gen.ts) и держит его в актуальном состоянии.
    // Ставится первым: он должен отработать до того, как React-плагин
    // начнёт трансформировать сгенерированный файл.
    // autoCodeSplitting: экран попадает в бандл, когда на него переходят, —
    // доска и карточка задачи не грузятся вместе со страницей входа.
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    // `@/shared/...` вместо `../../../shared/...`: относительный путь из
    // глубины features читается хуже, чем не читается вовсе.
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // Бэкенд поднимается отдельно: uv run python -m app.main
    proxy: {
      // API_TARGET задаёт Playwright: его бэкенд живёт на своём порту и своей базе.
      '/api': { target: process.env.API_TARGET ?? 'http://localhost:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // e2e/*.spec.ts — сценарии Playwright, Vitest их не запускает.
    include: ['src/**/*.test.{ts,tsx}'],
    css: true,
  },
})
