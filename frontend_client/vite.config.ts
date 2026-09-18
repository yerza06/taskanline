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
    tanstackRouter({ target: 'react' }),
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    // Бэкенд поднимается отдельно: uv run python -m app.main
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})
