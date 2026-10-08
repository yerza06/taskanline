import { screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { errorBody } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

describe('вход в админ-панель', () => {
  it('без сессии отправляет войти в веб-клиент — своего входа нет', async () => {
    server.use(
      http.post('/api/v1/admin/session', () => HttpResponse.json(errorBody('unauthorized'), { status: 401 })),
      http.post('/api/v1/auth/refresh', () => HttpResponse.json(errorBody('unauthorized'), { status: 401 })),
    )

    await renderApp({ path: '/' })

    expect(await screen.findByRole('heading', { name: 'Нужно войти' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Войти в TasKanLine' })).toHaveAttribute(
      'href',
      'http://localhost:5173/login',
    )
  })

  it('обычному пользователю — «не найдено», как и в API', async () => {
    server.use(
      http.post('/api/v1/admin/session', () => HttpResponse.json(errorBody('not_found'), { status: 404 })),
    )

    await renderApp({ path: '/users' })

    expect(await screen.findByText('Страница не найдена')).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Разделы' })).toBeNull()
  })

  it('администратору показывает обзор', async () => {
    await renderApp({ path: '/' })

    expect(await screen.findByText('41')).toBeInTheDocument()
    expect(screen.getByText(/0006_admin — актуальны/)).toBeInTheDocument()
    expect(screen.getByText('Пользователь заблокирован')).toBeInTheDocument()
  })
})
