import { screen, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { errorBody, TOKEN } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

const FULL_TOKEN = 'tkl_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG'

function created() {
  return http.post('/api/v1/me/tokens', () =>
    HttpResponse.json({ ...TOKEN, token: FULL_TOKEN }, { status: 201 }),
  )
}

async function issue(user: Awaited<ReturnType<typeof renderApp>>['user'], name = 'claude-code') {
  await user.type(await screen.findByLabelText('Название'), name)
  await user.click(screen.getByRole('button', { name: 'Выпустить токен' }))
}

describe('токены доступа', () => {
  it('на пустом списке объясняет, зачем они нужны', async () => {
    await renderApp({ path: '/tokens' })

    expect(await screen.findByText(/ни одного токена/i)).toBeInTheDocument()
  })

  it('перечисляет токены с префиксом и областью', async () => {
    server.use(http.get('/api/v1/me/tokens', () => HttpResponse.json({ items: [TOKEN] })))

    await renderApp({ path: '/tokens' })

    const row = await screen.findByRole('listitem')
    expect(within(row).getByText('claude-code')).toBeInTheDocument()
    expect(within(row).getByText('tkl_abcdefgh')).toBeInTheDocument()
    expect(within(row).getByText(/только чтение/i)).toBeInTheDocument()
    expect(within(row).getByText(/ни разу/i)).toBeInTheDocument()
  })

  it('выпускает токен и показывает полное значение один раз', async () => {
    server.use(created())
    const { user } = await renderApp({ path: '/tokens' })

    await issue(user)

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(FULL_TOKEN)).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: /готово/i }))

    expect(screen.queryByText(FULL_TOKEN)).not.toBeInTheDocument()
  })

  it('копирует выпущенный токен в буфер обмена', async () => {
    server.use(created())
    const { user } = await renderApp({ path: '/tokens' })

    await issue(user)

    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: /скопировать/i }))

    expect(await navigator.clipboard.readText()).toBe(FULL_TOKEN)
  })

  it('сообщает, если сервер отказал в выпуске', async () => {
    server.use(
      http.post('/api/v1/me/tokens', () =>
        HttpResponse.json(errorBody('insufficient_scope', 'Недостаточно прав'), { status: 403 }),
      ),
    )
    const { user } = await renderApp({ path: '/tokens' })

    await issue(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(/не хватает прав/i)
  })
})

describe('отзыв токена', () => {
  it('убирает токен из списка после подтверждения', async () => {
    let revoked = false
    server.use(
      http.get('/api/v1/me/tokens', () => HttpResponse.json({ items: revoked ? [] : [TOKEN] })),
      http.delete('/api/v1/me/tokens/:id', () => {
        revoked = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { user } = await renderApp({ path: '/tokens' })

    await user.click(await screen.findByRole('button', { name: /отозвать/i }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Отозвать' }))

    expect(await screen.findByText(/ни одного токена/i)).toBeInTheDocument()
    expect(revoked).toBe(true)
  })
})

describe('отмена отзыва', () => {
  it('оставляет токен на месте', async () => {
    let revoked = false
    server.use(
      http.get('/api/v1/me/tokens', () => HttpResponse.json({ items: [TOKEN] })),
      http.delete('/api/v1/me/tokens/:id', () => {
        revoked = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { user } = await renderApp({ path: '/tokens' })

    await user.click(await screen.findByRole('button', { name: /отозвать/i }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Отмена' }))

    expect(revoked).toBe(false)
    expect(await screen.findByRole('listitem')).toBeInTheDocument()
  })
})
