import { screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { errorBody, ME } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

async function fill(
  user: Awaited<ReturnType<typeof renderApp>>['user'],
  { password = 'correct horse battery' } = {},
) {
  await user.type(screen.getByLabelText('Email'), 'ivan@example.com')
  await user.type(screen.getByLabelText('Имя'), 'Иван Иванов')
  await user.type(screen.getByLabelText('Пароль'), password)
  await user.click(screen.getByRole('button', { name: 'Зарегистрироваться' }))
}

describe('экран регистрации', () => {
  it('требует пароль не короче восьми символов', async () => {
    let calls = 0
    server.use(
      http.post('/api/v1/auth/register', () => {
        calls += 1
        return HttpResponse.json({ user: ME }, { status: 201 })
      }),
    )
    const { user } = await renderApp({ path: '/register' })

    await screen.findByRole('button', { name: 'Зарегистрироваться' })
    await fill(user, { password: 'short' })

    expect(await screen.findByText('Пароль короче восьми символов')).toBeInTheDocument()
    expect(calls).toBe(0)
  })

  it('регистрирует и сразу открывает приложение', async () => {
    server.use(
      http.post('/api/v1/auth/register', () => HttpResponse.json({ user: ME }, { status: 201 })),
    )
    const { user, router } = await renderApp({ path: '/register' })

    await screen.findByRole('button', { name: 'Зарегистрироваться' })
    await fill(user)

    // Регистрация логинит: отдельного входа после неё не требуется.
    // Пространств ещё нет — корень ведёт создать первое.
    await screen.findByRole('heading', { name: 'Новое пространство' })
    expect(router.state.location.pathname).toBe('/onboarding')
  })

  it('сообщает о занятом email', async () => {
    server.use(
      http.post('/api/v1/auth/register', () =>
        HttpResponse.json(errorBody('email_already_registered', 'Занят'), { status: 409 }),
      ),
    )
    const { user } = await renderApp({ path: '/register' })

    await screen.findByRole('button', { name: 'Зарегистрироваться' })
    await fill(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(/уже зарегистрирован/i)
  })

  it('раскладывает ошибку валидации по полям формы', async () => {
    server.use(
      http.post('/api/v1/auth/register', () =>
        HttpResponse.json(
          errorBody('validation_error', 'Запрос не прошёл валидацию', {
            errors: [
              { loc: ['body', 'full_name'], msg: 'Имя не подходит', type: 'value_error' },
            ],
          }),
          { status: 422 },
        ),
      ),
    )
    const { user } = await renderApp({ path: '/register' })

    await screen.findByRole('button', { name: 'Зарегистрироваться' })
    await fill(user)

    expect(await screen.findByText('Имя не подходит')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('ведёт обратно на вход', async () => {
    const { user, router } = await renderApp({ path: '/register' })

    await user.click(await screen.findByRole('link', { name: /войти/i }))

    expect(router.state.location.pathname).toBe('/login')
  })
})
