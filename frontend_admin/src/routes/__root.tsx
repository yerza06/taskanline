import { useQuery, type QueryClient } from '@tanstack/react-query'
import { Outlet, createRootRouteWithContext } from '@tanstack/react-router'

import { AdminShell } from '@/app/AdminShell'
import { sessionQueryOptions } from '@/app/session'
import { ApiError } from '@/shared/api/client'

export interface RouterContext {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: Gate,
  notFoundComponent: () => <p className="text-fg-muted text-sm">Страница не найдена</p>,
})

// Своего входа у админки нет — сессия та же, что у веб-клиента (админ-спека §7).
const CLIENT_URL: string = (import.meta.env.VITE_CLIENT_URL as string | undefined) ?? 'http://localhost:5173'

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-canvas text-fg flex min-h-full items-center justify-center p-6 text-center">
      <div className="max-w-sm space-y-3">{children}</div>
    </div>
  )
}

/**
 * Вход в раздел: сессии нет — отправить в веб-клиент; обычный пользователь — «не
 * найдено», как и в API: о существовании админки ему знать незачем.
 */
function Gate() {
  const session = useQuery(sessionQueryOptions())
  if (session.isPending) return null
  if (session.error instanceof ApiError && session.error.status === 401) {
    return (
      <Centered>
        <h1 className="font-display text-xl font-semibold">Нужно войти</h1>
        <p className="text-fg-muted text-sm">
          У админ-панели нет своего входа: войдите в TasKanLine и вернитесь сюда.
        </p>
        <a href={`${CLIENT_URL}/login`} className="text-accent text-sm underline underline-offset-4">
          Войти в TasKanLine
        </a>
      </Centered>
    )
  }
  if (session.isError) {
    return (
      <Centered>
        <p className="text-fg-muted text-sm">Страница не найдена</p>
      </Centered>
    )
  }
  return (
    <AdminShell>
      <Outlet />
    </AdminShell>
  )
}
