import { Outlet, createFileRoute, redirect } from '@tanstack/react-router'

import { AppShell } from '@/app/AppShell'
import { sessionQueryOptions } from '@/features/auth/api/session'
import { ApiError } from '@/shared/api/client'

/**
 * Защищённая ветка маршрутов.
 *
 * Сессия запрашивается до отрисовки, а не внутри экрана: иначе человек сначала
 * увидит пустую страницу приложения и только потом — форму входа.
 */
export const Route = createFileRoute('/_authed')({
  beforeLoad: async ({ context, location }) => {
    try {
      await context.queryClient.ensureQueryData(sessionQueryOptions())
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        throw redirect({ to: '/login', search: { redirect: location.href } })
      }
      throw error
    }
  },
  component: AuthedLayout,
})

function AuthedLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  )
}
