import { screen, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { SESSION, SETTINGS, errorBody } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

describe('подтверждение паролем', () => {
  it('опасное действие спрашивает пароль и повторяется само', async () => {
    let confirmed = false
    let saved: unknown
    server.use(
      http.patch('/api/v1/admin/settings', async ({ request }) => {
        if (!confirmed) return HttpResponse.json(errorBody('reauth_required'), { status: 403 })
        saved = await request.json()
        return HttpResponse.json({ ...SETTINGS, instance_name: 'Acme' })
      }),
      http.post('/api/v1/admin/reauth', async ({ request }) => {
        const body = (await request.json()) as { password: string }
        if (body.password !== 'secret password') {
          return HttpResponse.json(errorBody('reauth_failed', 'Неверный пароль', { attempts_left: 2 }), {
            status: 403,
          })
        }
        confirmed = true
        return HttpResponse.json({ ...SESSION, reauth_until: '2026-10-08T10:15:00Z' })
      }),
    )
    const { user } = await renderApp({ path: '/settings' })

    const name = await screen.findByLabelText('Название инстанса')
    await user.clear(name)
    await user.type(name, 'Acme')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    const dialog = await screen.findByRole('dialog', { name: 'Подтвердите паролем' })
    await user.type(within(dialog).getByLabelText('Пароль'), 'wrong')
    await user.click(within(dialog).getByRole('button', { name: 'Подтвердить' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Неверный пароль')
    await user.type(within(dialog).getByLabelText('Пароль'), 'secret password')
    await user.click(within(dialog).getByRole('button', { name: 'Подтвердить' }))

    expect(await screen.findByText('Сохранено.')).toBeInTheDocument()
    expect(saved).toMatchObject({ instance_name: 'Acme', registration_mode: 'invite_only' })
  })
})
