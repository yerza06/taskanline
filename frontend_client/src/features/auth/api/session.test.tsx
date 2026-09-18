import { screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { anonymous, ME } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

function unauthorized() {
  return HttpResponse.json(
    { error: { code: 'unauthorized', message: 'Требуется аутентификация', details: {} } },
    { status: 401 },
  )
}

describe('защита маршрутов', () => {
  it('пускает аутентифицированного в профиль', async () => {
    const { router } = await renderApp({ path: '/profile' })

    expect(router.state.location.pathname).toBe('/profile')
    expect(await screen.findByRole('heading', { name: 'Профиль' })).toBeInTheDocument()
  })

  it('неаутентифицированного уводит на вход и запоминает, куда он шёл', async () => {
    server.use(...anonymous())

    const { router } = await renderApp({ path: '/tokens' })

    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.search).toEqual({ redirect: '/tokens' })
  })

  it('с корня ведёт в профиль', async () => {
    const { router } = await renderApp({ path: '/' })

    expect(router.state.location.pathname).toBe('/profile')
  })

  it('не запоминает чужой адрес как маршрут возврата', async () => {
    server.use(...anonymous())

    const { router } = await renderApp({ path: '/login?redirect=https://evil.example.com' })

    expect(router.state.location.search).toEqual({})
  })
})

describe('выход', () => {
  it('закрывает сессию на сервере и уводит на вход', async () => {
    let loggedOut = false
    server.use(
      http.post('/api/v1/auth/logout', () => {
        loggedOut = true
        return new HttpResponse(null, { status: 204 })
      }),
      http.get('/api/v1/me', () => (loggedOut ? unauthorized() : HttpResponse.json(ME))),
      http.post('/api/v1/auth/refresh', () => unauthorized()),
    )
    const { user, router } = await renderApp({ path: '/profile' })

    await user.click(await screen.findByRole('button', { name: /иван иванов/i }))
    await user.click(await screen.findByRole('menuitem', { name: /выйти/i }))

    expect(loggedOut).toBe(true)
    await screen.findByRole('heading', { name: 'Вход' })
    expect(router.state.location.pathname).toBe('/login')
  })
})
