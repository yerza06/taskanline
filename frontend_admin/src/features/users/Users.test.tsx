import { screen, waitFor, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { SESSION, USER, USER_ID } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

describe('пользователи', () => {
  it('ищет по email и имени', async () => {
    const queries: string[] = []
    server.use(
      http.get('/api/v1/admin/users', ({ request }) => {
        queries.push(new URL(request.url).search)
        return HttpResponse.json({ items: [], next_cursor: null, has_more: false })
      }),
    )
    const { user } = await renderApp({ path: '/users' })

    await user.type(await screen.findByLabelText('Поиск по email и имени'), 'пётр')
    await user.selectOptions(screen.getByLabelText('Статус'), 'blocked')

    await waitFor(() => expect(queries.at(-1)).toBe('?q=%D0%BF%D1%91%D1%82%D1%80&status=blocked'))
  })

  it('карточка: токены, входы, блокировка', async () => {
    let blocked = false
    server.use(
      http.post('/api/v1/admin/users/:id/block', () => {
        blocked = true
        return HttpResponse.json({ ...USER, status: 'blocked' })
      }),
    )
    const { user } = await renderApp({ path: `/users/${USER_ID}` })

    const tokens = await screen.findByRole('table', { name: 'Токены агентов' })
    expect(within(tokens).getByText('claude-code')).toBeInTheDocument()
    expect(screen.getByText(/10\.0\.0\.7/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Журнал по этому пользователю' })).toHaveAttribute(
      'href',
      `/audit?target_id=${USER_ID}`,
    )
    await user.click(screen.getByRole('button', { name: 'Заблокировать' }))

    expect(await screen.findByRole('status')).toHaveTextContent(/сессии и токены отозваны/)
    expect(blocked).toBe(true)
  })

  it('поддержке действий не показывает', async () => {
    server.use(http.post('/api/v1/admin/session', () => HttpResponse.json({ ...SESSION, role: 'support' })))

    await renderApp({ path: `/users/${USER_ID}` })

    await screen.findByRole('table', { name: 'Токены агентов' })
    expect(screen.queryByRole('group', { name: 'Действия' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Отозвать' })).toBeNull()
  })
})
