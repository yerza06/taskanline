import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'
import { TEAM_ID, World } from '@/test/msw/world'

describe('сохранение среза как view', () => {
  it('сохраняет фильтры, группировку и вид и открывает view', async () => {
    const world = new World()
    server.use(...world.handlers())
    const { user, router } = await renderApp({
      path: '/w/acme/team/ENG?group=priority&filters=%7B%22label_id%22%3A%7B%22op%22%3A%22in%22%2C%22value%22%3A%5B%22019a5c1e-0000-7000-8000-0000000000e0%22%5D%7D%7D',
    })

    await user.click(await screen.findByRole('button', { name: 'Сохранить как view' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Название'), 'Баги')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))

    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/w\/acme\/view\//))
    expect(world.sent.find((s) => s.path === '/views')?.body).toMatchObject({
      name: 'Баги',
      scope: 'user',
      group_by: 'priority',
      layout: 'list',
      filters: {
        label_id: { op: 'in', value: ['019a5c1e-0000-7000-8000-0000000000e0'] },
        team_id: { op: 'in', value: [TEAM_ID] },
      },
    })
  })
})
