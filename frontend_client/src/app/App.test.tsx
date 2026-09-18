import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderApp } from '../test/render'

describe('App', () => {
  it('с корня уводит на экран входа', async () => {
    const { router } = await renderApp({ path: '/' })

    expect(router.state.location.pathname).toBe('/login')
    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument()
  })

  it('на неизвестном маршруте показывает страницу «не найдено»', async () => {
    await renderApp({ path: '/nowhere' })

    expect(await screen.findByText(/страница не найдена/i)).toBeInTheDocument()
  })
})
