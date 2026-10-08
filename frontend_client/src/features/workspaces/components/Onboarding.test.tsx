import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'
import { World } from '@/test/msw/world'

describe('первое пространство', () => {
  it('slug следует за названием, после создания — внутрь пространства', async () => {
    const world = new World()
    world.workspaces = []
    server.use(...world.handlers())
    const { user, router } = await renderApp({ path: '/onboarding' })

    await user.type(await screen.findByLabelText('Название'), 'My Team')
    expect(screen.getByLabelText('Адрес')).toHaveValue('my-team')
    await user.click(screen.getByRole('button', { name: 'Создать пространство' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/w/my-team'))
  })
})
