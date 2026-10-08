import { screen, waitFor, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { ME } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'
import { WS_ID, World } from '@/test/msw/world'

describe('входящие', () => {
  it('показывает уведомление со ссылкой на задачу и отмечает прочитанным', async () => {
    const world = new World()
    let read = false
    const notification = {
      id: '019a5c1e-0000-7000-8000-0000000000f0',
      workspace_id: WS_ID,
      type: 'assigned',
      task_id: world.tasks[0]!.id,
      comment_id: null,
      actor_id: ME.id,
      created_at: '2026-10-08T10:00:00Z',
    }
    server.use(
      http.get('/api/v1/me/notifications', () =>
        HttpResponse.json({
          items: [{ ...notification, read_at: read ? '2026-10-08T11:00:00Z' : null }],
          next_cursor: null,
          has_more: false,
        }),
      ),
      http.post('/api/v1/me/notifications/:id/read', () => {
        read = true
        return HttpResponse.json({ ...notification, read_at: '2026-10-08T11:00:00Z' })
      }),
      ...world.handlers(),
    )
    const { user } = await renderApp({ path: '/w/acme/inbox' })

    // Пунктов списка на странице много (боковое меню) — берём строку уведомления.
    const text = await screen.findByText(/назначил\(а\) на вас/)
    const item = text.closest('li')
    if (!item) throw new Error('Уведомление не в списке')
    expect(await within(item).findByRole('link', { name: 'ENG-1 Починить логин' })).toBeInTheDocument()
    await user.click(within(item).getByRole('button', { name: 'Прочитано' }))

    await waitFor(() => expect(within(item).queryByRole('button', { name: 'Прочитано' })).toBeNull())
    expect(read).toBe(true)
  })
})
