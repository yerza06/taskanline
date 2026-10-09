import { RouterProvider } from '@tanstack/react-router'
import { useState } from 'react'

import { Providers } from './Providers'
import { createAppQueryClient } from './query-client'
import { createAppRouter } from './router'

/**
 * Корень приложения.
 *
 * Клиент запросов и роутер создаются один раз на жизнь вкладки: пересоздание
 * на каждом рендере обнуляло бы кэш и историю навигации.
 */
export function App() {
  const [queryClient] = useState(createAppQueryClient)
  const [router] = useState(() => createAppRouter(queryClient))

  return (
    <Providers queryClient={queryClient}>
      <RouterProvider router={router} />
    </Providers>
  )
}
