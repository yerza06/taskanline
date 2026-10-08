import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'
import { STATES, World } from '@/test/msw/world'

describe('карточка задачи', () => {
  it('меняет статус и пишет комментарий', async () => {
    const world = new World()
    server.use(...world.handlers())
    const { user } = await renderApp({ path: '/w/acme/task/eng-1' })

    await user.selectOptions(await screen.findByLabelText('Статус'), 'In Progress')
    await user.type(screen.getByLabelText('Комментарий'), 'Взял в работу')
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await waitFor(() =>
      expect(world.sent.map((s) => [s.method, s.body])).toEqual([
        ['PATCH', { state_id: STATES[1]!.id }],
        ['POST', { body: 'Взял в работу' }],
      ]),
    )
  })

  it('описание — Markdown без сырого HTML', async () => {
    const world = new World()
    world.tasks[0]!.description = '**важно**\n\n<img src=x onerror="alert(1)">'
    server.use(...world.handlers())

    await renderApp({ path: '/w/acme/task/ENG-1' })

    expect(await screen.findByText('важно')).toContainHTML('<strong>важно</strong>')
    expect(document.querySelector('img')).toBeNull()
  })

  it('чужая задача — не найдена', async () => {
    server.use(...new World().handlers())

    await renderApp({ path: '/w/acme/task/ENG-999' })

    expect(await screen.findByText(/ENG-999 не найдена/)).toBeInTheDocument()
  })
})
