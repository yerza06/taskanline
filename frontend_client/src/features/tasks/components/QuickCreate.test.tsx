import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'
import { TEAM_ID, World } from '@/test/msw/world'

describe('быстрое создание задачи', () => {
  it('клавиша c открывает окно, Enter создаёт задачу и ведёт в неё', async () => {
    const world = new World()
    server.use(...world.handlers())
    const { user, router } = await renderApp({ path: '/w/acme/team/ENG' })
    await screen.findByRole('region', { name: 'Todo' })

    await user.keyboard('c')
    await user.type(await screen.findByLabelText('Название'), 'Новая задача{Enter}')

    await waitFor(() => expect(router.state.location.pathname).toBe('/w/acme/task/ENG-4'))
    expect(world.sent.find((s) => s.path === '/tasks')?.body).toMatchObject({
      title: 'Новая задача',
      team_id: TEAM_ID,
      priority: 0,
    })
  })
})
