import { screen, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { errorBody, ME } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

describe('профиль', () => {
  it('показывает email, имя и роль инстанса', async () => {
    await renderApp({ path: '/profile' })

    // Роль видна и в шапке, и на экране — сужаем поиск до самого экрана.
    const main = await screen.findByRole('main')
    expect(await within(main).findByDisplayValue('Иван Иванов')).toBeInTheDocument()
    expect(within(main).getByText('ivan@example.com')).toBeInTheDocument()
    expect(within(main).getByText('Суперадминистратор')).toBeInTheDocument()
  })

  it('сохраняет новое имя и обновляет шапку', async () => {
    server.use(
      http.patch('/api/v1/me', async ({ request }) => {
        const body = (await request.json()) as { full_name?: string }
        return HttpResponse.json({ ...ME, full_name: body.full_name })
      }),
    )
    const { user } = await renderApp({ path: '/profile' })

    const name = await screen.findByLabelText('Имя')
    await user.clear(name)
    await user.type(name, 'Иван Петров')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    expect(await within(screen.getByRole('banner')).findByText('Иван Петров')).toBeInTheDocument()
  })

  it('сообщает об отказе сервера и не выдаёт изменение за сохранённое', async () => {
    server.use(
      http.patch('/api/v1/me', () =>
        HttpResponse.json(errorBody('internal_error', 'Внутренняя ошибка'), { status: 500 }),
      ),
    )
    const { user } = await renderApp({ path: '/profile' })

    const name = await screen.findByLabelText('Имя')
    await user.clear(name)
    await user.type(name, 'Иван Петров')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/ошибка сервера/i)
    expect(within(screen.getByRole('banner')).getByText('Иван Иванов')).toBeInTheDocument()
  })

  it('под токеном только на чтение не даёт сохранять', async () => {
    server.use(
      http.get('/api/v1/me', () =>
        HttpResponse.json({ ...ME, auth_method: 'token', scopes: ['read'] }),
      ),
    )
    await renderApp({ path: '/profile' })

    expect(await screen.findByRole('button', { name: 'Сохранить' })).toBeDisabled()
  })

  it('переключает тему тремя состояниями', async () => {
    const { user } = await renderApp({ path: '/profile' })

    await user.click(await screen.findByRole('radio', { name: 'Тёмная' }))
    expect(document.documentElement).toHaveClass('dark')

    await user.click(screen.getByRole('radio', { name: 'Светлая' }))
    expect(document.documentElement).not.toHaveClass('dark')

    await user.click(screen.getByRole('radio', { name: 'Системная' }))
    expect(localStorage.getItem('taskanline.theme')).toBe('system')
  })

  it('выход закрывает сессию на сервере и уводит на вход', async () => {
    let loggedOut = false
    server.use(
      http.post('/api/v1/auth/logout', () => {
        loggedOut = true
        return new HttpResponse(null, { status: 204 })
      }),
      http.get('/api/v1/me', () =>
        loggedOut
          ? HttpResponse.json(errorBody('unauthorized', 'Требуется аутентификация'), {
              status: 401,
            })
          : HttpResponse.json(ME),
      ),
      http.post('/api/v1/auth/refresh', () =>
        HttpResponse.json(errorBody('unauthorized', 'Требуется аутентификация'), { status: 401 }),
      ),
    )
    const { user, router } = await renderApp({ path: '/profile' })

    await user.click(await screen.findByRole('button', { name: 'Выйти' }))

    expect(loggedOut).toBe(true)
    await screen.findByRole('heading', { name: 'Вход' })
    expect(router.state.location.pathname).toBe('/login')
  })
})
