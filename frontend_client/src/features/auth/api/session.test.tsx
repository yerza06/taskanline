import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { anonymous } from '@/test/msw/handlers'
import { world } from '@/test/msw/world'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

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

  it('с корня без пространств ведёт создать своё', async () => {
    const { router } = await renderApp({ path: '/' })

    expect(router.state.location.pathname).toBe('/onboarding')
  })

  it('с корня ведёт в первое пространство', async () => {
    server.use(...world())

    const { router } = await renderApp({ path: '/' })

    await waitFor(() => expect(router.state.location.pathname).toBe('/w/acme'))
  })

  it('не запоминает чужой адрес как маршрут возврата', async () => {
    server.use(...anonymous())

    const { router } = await renderApp({ path: '/login?redirect=https://evil.example.com' })

    expect(router.state.location.search).toEqual({})
  })
})
