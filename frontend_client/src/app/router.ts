import type { QueryClient } from '@tanstack/react-query'
import { createRouter, type RouterHistory } from '@tanstack/react-router'

import { routeTree } from '../routeTree.gen'

/**
 * Роутер с типизированным контекстом: маршруты получают `queryClient` и
 * подгружают данные в `beforeLoad`/`loader` до первой отрисовки экрана.
 *
 * `history` передаётся только в тестах — там нужна память вместо адресной строки.
 */
export function createAppRouter(queryClient: QueryClient, history?: RouterHistory) {
  return createRouter({
    routeTree,
    context: { queryClient },
    defaultPreload: 'intent',
    history,
  })
}

declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof createAppRouter>
  }
}
