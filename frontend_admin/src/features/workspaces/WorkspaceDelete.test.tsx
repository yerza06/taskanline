import { screen, waitFor, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { WS_ID } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

describe('удаление пространства', () => {
  it('требует ввести название руками', async () => {
    let deleted = false
    server.use(
      http.delete('/api/v1/admin/workspaces/:id', () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { user, router } = await renderApp({ path: `/workspaces/${WS_ID}` })

    expect(await screen.findByRole('table', { name: 'Участники' })).toHaveTextContent('leaver@example.com')
    await user.click(screen.getByRole('button', { name: 'Удалить пространство' }))
    const dialog = await screen.findByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Удалить навсегда' })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText(/Введите название/), 'Acme')
    await user.click(confirm)

    await waitFor(() => expect(router.state.location.pathname).toBe('/workspaces'))
    expect(deleted).toBe(true)
  })
})
