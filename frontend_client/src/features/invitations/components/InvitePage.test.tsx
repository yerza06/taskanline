import { screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { ME, anonymous, errorBody, invitation, signedIn, unauthorized } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'
import { world } from '@/test/msw/world'

const TOKEN = 'abc123'
const ACCEPT = `/api/v1/invitations/token/${TOKEN}/accept`
const ACCEPTED = { workspace_id: 'w', scope_type: 'project', scope_id: 'p', role: 'member' }

describe('страница приглашения', () => {
  it('новый человек заводит учётную запись и принимает', async () => {
    let accepted = false
    let body: unknown
    server.use(
      // Первым: внутри одного use выигрывает обработчик, стоящий раньше, а
      // anonymous() тоже отвечает на /me. После принятия сессия уже открыта.
      http.get('/api/v1/me', () =>
        accepted ? HttpResponse.json({ ...ME, email: 'anna@example.com' }) : unauthorized(),
      ),
      ...anonymous(),
      ...invitation(),
      ...world(),
      http.post(ACCEPT, async ({ request }) => {
        body = await request.json()
        accepted = true
        return HttpResponse.json(ACCEPTED)
      }),
    )
    const { user, router } = await renderApp({ path: `/invite/${TOKEN}` })

    expect(await screen.findByText(/Ольга Владелец приглашает вас в «Acme»/)).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveValue('anna@example.com')
    await user.type(screen.getByLabelText('Имя'), 'Анна')
    await user.type(screen.getByLabelText('Пароль'), 'correct horse battery')
    await user.click(screen.getByRole('button', { name: /принять/i }))

    // Принятое приглашение — членство: корень ведёт в пространство, куда позвали.
    await screen.findByRole('heading', { name: 'Мои задачи' })
    expect(router.state.location.pathname).toBe('/w/acme')
    expect(body).toEqual({ full_name: 'Анна', password: 'correct horse battery' })
  })

  it('вошедший с тем же адресом принимает одной кнопкой', async () => {
    let calls = 0
    server.use(
      ...signedIn({ email: 'anna@example.com' }),
      ...invitation(),
      ...world(),
      http.post(ACCEPT, () => {
        calls += 1
        return HttpResponse.json(ACCEPTED)
      }),
    )
    const { user } = await renderApp({ path: `/invite/${TOKEN}` })

    await user.click(await screen.findByRole('button', { name: 'Принять приглашение' }))

    await screen.findByRole('heading', { name: 'Мои задачи' })
    expect(calls).toBe(1)
  })

  it('вошедшему с другим адресом не предлагает принять', async () => {
    server.use(...signedIn(), ...invitation())
    await renderApp({ path: `/invite/${TOKEN}` })

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /отправлено на anna@example\.com.*ivan@example\.com/,
    )
    expect(screen.queryByRole('button', { name: /принять/i })).not.toBeInTheDocument()
  })

  it('сообщает об истёкшем приглашении', async () => {
    server.use(...anonymous(), ...invitation({ status: 'expired' }))
    await renderApp({ path: `/invite/${TOKEN}` })

    expect(await screen.findByRole('alert')).toHaveTextContent(/срок приглашения истёк/i)
  })

  it('сообщает о неизвестной ссылке', async () => {
    server.use(
      ...anonymous(),
      http.get('/api/v1/invitations/token/:token', () =>
        HttpResponse.json(errorBody('invitation_not_found'), { status: 404 }),
      ),
    )
    await renderApp({ path: `/invite/${TOKEN}` })

    expect(await screen.findByRole('alert')).toHaveTextContent(/не найдено/i)
  })

  it('отправляет на вход, если учётная запись уже есть', async () => {
    server.use(
      ...anonymous(),
      ...invitation(),
      http.post(ACCEPT, () =>
        HttpResponse.json(errorBody('login_required'), { status: 409 }),
      ),
    )
    const { user } = await renderApp({ path: `/invite/${TOKEN}` })

    await user.type(await screen.findByLabelText('Имя'), 'Анна')
    await user.type(screen.getByLabelText('Пароль'), 'correct horse battery')
    await user.click(screen.getByRole('button', { name: /принять/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/войдите/i)
    expect(screen.getByRole('link', { name: 'Войти' })).toHaveAttribute(
      'href',
      expect.stringContaining(encodeURIComponent(`/invite/${TOKEN}`)),
    )
  })
})
