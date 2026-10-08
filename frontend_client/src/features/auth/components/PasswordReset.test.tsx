import { screen, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { anonymous, errorBody, ME } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

describe('смена пароля', () => {
  it('«забыл пароль» отвечает одинаково для любого адреса', async () => {
    let body: unknown
    server.use(
      ...anonymous(),
      http.post('/api/v1/auth/forgot-password', async ({ request }) => {
        body = await request.json()
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { user } = await renderApp({ path: '/forgot-password' })

    await user.type(await screen.findByLabelText('Email'), 'ghost@example.com')
    await user.click(screen.getByRole('button', { name: 'Прислать ссылку' }))

    expect(await screen.findByRole('status')).toHaveTextContent(/Если адрес ghost@example.com зарегистрирован/)
    expect(body).toEqual({ email: 'ghost@example.com' })
  })

  it('новый пароль по ссылке входит и ведёт в приложение', async () => {
    let sent: unknown
    let reset = false
    server.use(
      http.get('/api/v1/me', () =>
        reset ? HttpResponse.json(ME) : HttpResponse.json(errorBody('unauthorized'), { status: 401 }),
      ),
      ...anonymous(),
      http.post('/api/v1/auth/reset-password', async ({ request }) => {
        sent = await request.json()
        reset = true
        return HttpResponse.json({ user: ME })
      }),
    )
    const { user, router } = await renderApp({ path: '/reset-password/tok123' })

    await user.type(await screen.findByLabelText('Новый пароль'), 'brand new password')
    await user.click(screen.getByRole('button', { name: 'Сменить пароль и войти' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/onboarding'))
    expect(sent).toEqual({ token: 'tok123', password: 'brand new password' })
  })

  it('устаревшая ссылка — понятный отказ', async () => {
    server.use(
      ...anonymous(),
      http.post('/api/v1/auth/reset-password', () =>
        HttpResponse.json(errorBody('reset_token_invalid'), { status: 400 }),
      ),
    )
    const { user } = await renderApp({ path: '/reset-password/old' })

    await user.type(await screen.findByLabelText('Новый пароль'), 'brand new password')
    await user.click(screen.getByRole('button', { name: 'Сменить пароль и войти' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/запросите новую/)
  })
})

describe('регистрация по приглашению', () => {
  it('предупреждает, что сервер закрыт', async () => {
    server.use(
      ...anonymous(),
      http.get('/api/v1/instance', () =>
        HttpResponse.json({ instance_name: 'Acme', registration_mode: 'invite_only' }),
      ),
    )

    await renderApp({ path: '/register' })

    expect(await screen.findByRole('note')).toHaveTextContent(/только по приглашению/)
  })
})
