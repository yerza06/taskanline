import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'
import { World } from '@/test/msw/world'

describe('горячие клавиши', () => {
  it('? открывает справку, g затем i ведёт во входящие', async () => {
    server.use(...new World().handlers())
    const { user, router } = await renderApp({ path: '/w/acme' })
    await screen.findByRole('heading', { name: 'Мои задачи' })

    await user.keyboard('?')
    expect(await screen.findByRole('dialog', { name: 'Горячие клавиши' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await user.keyboard('gi')

    expect(router.state.location.pathname).toBe('/w/acme/inbox')
  })
})
