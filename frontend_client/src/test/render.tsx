import { QueryClient } from '@tanstack/react-query'
import { RouterProvider, createMemoryHistory } from '@tanstack/react-router'
import { render, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Providers } from '@/app/Providers'
import { createAppQueryClient } from '@/app/query-client'
import { createAppRouter } from '@/app/router'

/**
 * Поднимает приложение на памяти вместо адресной строки.
 *
 * Свой `QueryClient` на тест: общий кэш превращает соседние тесты в зависимые,
 * а `gcTime: 0` не даёт данным пережить размонтирование.
 */
export async function renderApp({
  path = '/',
  appCache = false,
}: {
  path?: string
  /** Кэш как в приложении: данные без наблюдателей живут минуты, а не исчезают сразу. */
  appCache?: boolean
} = {}) {
  const queryClient = appCache
    ? createAppQueryClient()
    : new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const router = createAppRouter(queryClient, createMemoryHistory({ initialEntries: [path] }))

  const result = render(
    <Providers queryClient={queryClient}>
      <RouterProvider router={router} />
    </Providers>,
  )

  // Первая навигация асинхронная: без ожидания тест видит пустую разметку.
  await waitFor(() => {
    if (router.state.status !== 'idle') {
      throw new Error('Роутер ещё не готов')
    }
  })

  return { ...result, router, queryClient, user: userEvent.setup() }
}
