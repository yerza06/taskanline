import { QueryClient } from '@tanstack/react-query'

/**
 * Клиент запросов приложения.
 *
 * `retry: false` — повторять `401`, `403` и `422` бессмысленно, а обновление
 * протухшей сессии берёт на себя http-клиент, а не механизм повторов.
 * `refetchOnWindowFocus` компенсирует отсутствие realtime (архитектура §4.5):
 * возврат на вкладку подтягивает изменения, сделанные в другом месте.
 */
export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: true,
        staleTime: 30_000,
      },
    },
  })
}
