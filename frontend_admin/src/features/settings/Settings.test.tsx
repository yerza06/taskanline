import { screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { SESSION } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

describe('настройки инстанса', () => {
  it('предупреждает об открытой регистрации', async () => {
    const { user } = await renderApp({ path: '/settings' })

    await user.selectOptions(await screen.findByLabelText('Регистрация'), 'open')

    expect(screen.getByRole('note')).toHaveTextContent(/любому, кто до него дотянется/)
  })

  it('администратору без superadmin — только чтение', async () => {
    server.use(http.post('/api/v1/admin/session', () => HttpResponse.json({ ...SESSION, role: 'admin' })))

    await renderApp({ path: '/settings' })

    expect(await screen.findByLabelText('Название инстанса')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Сохранить' })).toBeNull()
  })
})
