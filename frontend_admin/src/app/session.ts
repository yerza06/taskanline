import { queryOptions, useQuery } from '@tanstack/react-query'

import { adminFetch } from '@/shared/api/admin'
import type { AdminSession, InstanceRole } from '@/shared/api/types'

export const SESSION_KEY = ['admin-session'] as const

/**
 * Сессия администратора. Открывается `POST /admin/session` один раз за жизнь
 * вкладки — это запись `admin_login` в журнале, повторять её на каждый экран незачем.
 */
export function sessionQueryOptions() {
  return queryOptions({
    queryKey: SESSION_KEY,
    queryFn: () => adminFetch<AdminSession>('/session', { method: 'POST' }),
    staleTime: Infinity,
    retry: false,
  })
}

export function useAdminSession(): AdminSession | undefined {
  return useQuery(sessionQueryOptions()).data
}

const RANK: Record<InstanceRole, number> = { user: 0, support: 1, admin: 2, superadmin: 3 }

/** Есть ли у текущего администратора роль не ниже нужной — чтобы не показывать лишних кнопок. */
export function useCan(minimum: InstanceRole): boolean {
  const session = useAdminSession()
  return session ? RANK[session.role] >= RANK[minimum] : false
}
