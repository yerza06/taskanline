import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'
import { STATES, TEAM_ID, World } from '@/test/msw/world'

describe('задачи команды', () => {
  it('показывает задачи по статусам и спрашивает только свою команду', async () => {
    const world = new World()
    server.use(...world.handlers())

    await renderApp({ path: '/w/acme/team/ENG' })

    const todo = await screen.findByRole('region', { name: 'Todo' })
    expect(within(todo).getByRole('link', { name: 'Починить логин' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'In Progress' })).toHaveTextContent('Выкатить релиз')
    expect(world.lastQuery).toMatchObject({
      filters: { team_id: { op: 'in', value: [TEAM_ID] } },
      group_by: 'state',
      sort_by: 'manual',
    })
  })

  it('доска показывает все статусы команды, включая пустые', async () => {
    server.use(...new World().handlers())

    await renderApp({ path: '/w/acme/team/ENG?layout=board' })

    for (const state of STATES) {
      expect(await screen.findByRole('region', { name: state.name })).toBeInTheDocument()
    }
    expect(screen.getAllByRole('button', { name: /^Переместить ENG-/ })).toHaveLength(3)
  })

  it('вид и группировка живут в адресе', async () => {
    server.use(...new World().handlers())
    const { user, router } = await renderApp({ path: '/w/acme/team/ENG' })

    await user.selectOptions(await screen.findByLabelText('Группировка'), 'priority')

    await waitFor(() => expect(router.state.location.search).toEqual({ group: 'priority' }))
  })

  it('чужая команда — не найдена', async () => {
    server.use(...new World().handlers())

    await renderApp({ path: '/w/acme/team/DES' })

    expect(await screen.findByText(/Команда не найден/)).toBeInTheDocument()
  })
})
