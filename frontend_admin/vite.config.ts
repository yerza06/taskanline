import { fileURLToPath } from 'node:url'

import { tanstackRouter } from '@tanstack/router-plugin/vite'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/**
 * Админ-панель — отдельное приложение со своим бандлом и своим хостом (админ-спека §2):
 * её код не попадает в бандл пользователя. Сессия общая с веб-клиентом — та же
 * cookie, поэтому API проксируется на тот же бэкенд.
 */
export default defineConfig({
  plugins: [tanstackRouter({ target: 'react', autoCodeSplitting: true }), react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5175,
    // Токены темы — общие с веб-клиентом, лежат в ../frontend_shared.
    fs: { allow: ['.', '../frontend_shared'] },
    proxy: {
      '/api': { target: process.env.API_TARGET ?? 'http://localhost:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
