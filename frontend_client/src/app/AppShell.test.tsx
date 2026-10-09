import { screen, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { ME } from '@/test/msw/handlers'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/render'

// Тесты, открывающие меню Radix, разнесены по файлам намеренно: перехватчик
// указателя, оставшийся от меню предыдущего теста, съедает первое нажатие в
// следующем. Vitest изолирует файлы друг от друга, тесты внутри файла — нет.

describe('оболочка приложения', () => {
  it('показывает имя пользователя и его роль инстанса', async () => {
    await renderApp({ path: '/profile' })

    const header = await screen.findByRole('banner')
    expect(header).toHaveTextContent('Иван Иванов')
    expect(header).toHaveTextContent(/суперадминистратор/i)
  })

  it('под токеном только на чтение предупреждает, что изменения недоступны', async () => {
    server.use(
      http.get('/api/v1/me', () =>
        HttpResponse.json({ ...ME, auth_method: 'token', scopes: ['read'] }),
      ),
    )

    await renderApp({ path: '/profile' })

    const header = await screen.findByRole('banner')
    expect(within(header).getByText(/только чтение/i)).toBeInTheDocument()
  })

  it('даёт в меню переход к токенам доступа', async () => {
    const { user, router } = await renderApp({ path: '/profile' })

    await user.click(await screen.findByRole('button', { name: /иван иванов/i }))
    await user.click(await screen.findByRole('menuitem', { name: /токены доступа/i }))

    expect(router.state.location.pathname).toBe('/tokens')
  })
})
