import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { ThemeProvider } from '../shared/theme/ThemeProvider'

/** Общая обвязка приложения и тестов: тема снаружи, кэш запросов внутри. */
export function Providers({ queryClient, children }: { queryClient: QueryClient; children: ReactNode }) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ThemeProvider>
  )
}
