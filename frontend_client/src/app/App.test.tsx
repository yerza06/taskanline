import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderApp } from '@/test/render'

describe('App', () => {
  it('на неизвестном маршруте показывает страницу «не найдено»', async () => {
    await renderApp({ path: '/nowhere' })

    expect(await screen.findByText(/страница не найдена/i)).toBeInTheDocument()
  })
})
