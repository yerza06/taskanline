import { screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { errorBody, ME } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

async function fillAndSubmit(
  user: ReturnType<typeof renderApp> extends Promise<infer R>
    ? R extends { user: infer U }
      ? U
      : never
    : never,
  { email = 'ivan@example.com', password = 'correct horse battery' } = {},
) {
  await user.type(screen.getByLabelText(/email/i), email)
  await user.type(screen.getByLabelText(/пароль/i), password)
  await user.click(screen.getByRole('button', { name: 'Войти' }))
}

describe('экран входа', () => {
  it('не отправляет пустую форму и показывает ошибки полей', async () => {
    let calls = 0
    server.use(
      http.post('/api/v1/auth/login', () => {
        calls += 1
        return HttpResponse.json({ user: ME })
      }),
    )
    const { user } = await renderApp({ path: '/login' })

    await user.click(await screen.findByRole('button', { name: 'Войти' }))

    expect(await screen.findByText(/укажите email/i)).toBeInTheDocument()
    expect(screen.getByText(/введите пароль/i)).toBeInTheDocument()
    expect(calls).toBe(0)
  })

  it('входит и открывает приложение', async () => {
    server.use(http.post('/api/v1/auth/login', () => HttpResponse.json({ user: ME })))
    const { user, router } = await renderApp({ path: '/login' })

    await screen.findByRole('button', { name: 'Войти' })
    await fillAndSubmit(user)

    // Пространств ещё нет — корень ведёт создать первое.
    await screen.findByRole('heading', { name: 'Новое пространство' })
    expect(router.state.location.pathname).toBe('/onboarding')
  })

  it('возвращает туда, куда человек шёл до входа', async () => {
    server.use(http.post('/api/v1/auth/login', () => HttpResponse.json({ user: ME })))
    const { user, router } = await renderApp({ path: '/login?redirect=/tokens' })

    await screen.findByRole('button', { name: 'Войти' })
    await fillAndSubmit(user)

    await screen.findByRole('heading', { name: 'Токены доступа' })
    expect(router.state.location.pathname).toBe('/tokens')
  })

  it('на неверной паре отвечает одним сообщением, не выдавая, что именно не сошлось', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json(errorBody('invalid_credentials', 'Неверный email или пароль'), {
          status: 401,
        }),
      ),
    )
    const { user } = await renderApp({ path: '/login' })

    await screen.findByRole('button', { name: 'Войти' })
    await fillAndSubmit(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(/неверный email или пароль/i)
  })

  it('на превышении лимита попыток называет, сколько ждать', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json(errorBody('rate_limited', 'Слишком часто', { retry_after: 42 }), {
          status: 429,
        }),
      ),
    )
    const { user } = await renderApp({ path: '/login' })

    await screen.findByRole('button', { name: 'Войти' })
    await fillAndSubmit(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('42')
  })

  it('на время запроса кнопка недоступна', async () => {
    server.use(
      http.post('/api/v1/auth/login', async () => {
        await new Promise((resolve) => setTimeout(resolve, 50))
        return HttpResponse.json({ user: ME })
      }),
    )
    const { user } = await renderApp({ path: '/login' })

    await screen.findByRole('button', { name: 'Войти' })
    await fillAndSubmit(user)

    expect(screen.getByRole('button', { name: /вход/i })).toBeDisabled()
  })

  it('ведёт на регистрацию', async () => {
    const { user, router } = await renderApp({ path: '/login' })

    await user.click(await screen.findByRole('link', { name: /зарегистрироваться/i }))

    expect(router.state.location.pathname).toBe('/register')
  })
})
