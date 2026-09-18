import { HttpResponse, http, type HttpHandler } from 'msw'

import type { Me, TokenRead } from '../../shared/api/types'

export const ME: Me = {
  id: '019a5c1e-0000-7000-8000-000000000001',
  email: 'ivan@example.com',
  full_name: 'Иван Иванов',
  avatar_url: null,
  role: 'superadmin',
  created_at: '2026-09-18T10:00:00Z',
  auth_method: 'session',
  scopes: ['read', 'write'],
}

export const TOKEN: TokenRead = {
  id: '019a5c1e-0000-7000-8000-000000000002',
  name: 'claude-code',
  prefix: 'tkl_abcdefgh',
  scope: 'read',
  expires_at: null,
  last_used_at: null,
  created_at: '2026-09-18T11:00:00Z',
}

/** Конверт ошибки по контракту §3.6 — тот же, что отдаёт бэкенд. */
export function errorBody(code: string, message = 'Ошибка', details: object = {}) {
  return { error: { code, message, details } }
}

export function unauthorized() {
  return HttpResponse.json(errorBody('unauthorized', 'Требуется аутентификация'), { status: 401 })
}

/** Никто не вошёл: и профиль, и обновление сессии отвечают 401. */
export function anonymous(): HttpHandler[] {
  return [
    http.get('/api/v1/me', () => unauthorized()),
    http.post('/api/v1/auth/refresh', () => unauthorized()),
  ]
}

export function signedIn(user: Partial<Me> = {}): HttpHandler[] {
  return [http.get('/api/v1/me', () => HttpResponse.json({ ...ME, ...user }))]
}

export function tokens(items: TokenRead[]): HttpHandler[] {
  return [http.get('/api/v1/me/tokens', () => HttpResponse.json({ items }))]
}

export function defaultHandlers(): HttpHandler[] {
  return [...signedIn(), ...tokens([])]
}
