import { screen, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { ENTRY, USER_ID } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

describe('журнал аудита', () => {
  it('фильтр по цели из адреса и по действию; payload в строке', async () => {
    const queries: string[] = []
    server.use(
      http.get('/api/v1/admin/audit', ({ request }) => {
        queries.push(new URL(request.url).search)
        return HttpResponse.json({ items: [ENTRY], next_cursor: null, has_more: false })
      }),
    )
    const { user } = await renderApp({ path: `/audit?target_id=${USER_ID}` })

    // jsdom не раскрывает <details> по щелчку — проверяем, что payload в разметке.
    expect(await screen.findByText('Пользователь заблокирован')).toBeInTheDocument()
    expect(screen.getByText(/"email": "leaver@example.com"/)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Действие'), 'user_blocked')

    await waitFor(() =>
      expect(Object.fromEntries(new URLSearchParams(queries.at(-1)))).toEqual({
        action: 'user_blocked',
        target_id: USER_ID,
      }),
    )
  })
})
