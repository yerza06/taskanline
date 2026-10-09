import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, Link, Outlet } from '@tanstack/react-router'

export interface RouterContext {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
  notFoundComponent: NotFound,
})

function NotFound() {
  return (
    <div className="bg-canvas text-fg flex min-h-full flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-fg-muted text-sm">Страница не найдена</p>
      <Link to="/" className="text-accent text-sm underline underline-offset-4">
        На главную
      </Link>
    </div>
  )
}
