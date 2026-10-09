import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'

import { apiFetch } from '@/shared/api/client'
import type { Me } from '@/shared/api/types'

/** Ключ кэша сессии: его знают и защита маршрутов, и вход, и профиль. */
export const SESSION_KEY = ['session'] as const

export function sessionQueryOptions() {
  return queryOptions({
    queryKey: SESSION_KEY,
    queryFn: () => apiFetch<Me>('/me'),
    // Профиль спрашивает каждый экран, а меняется он редко.
    staleTime: 5 * 60_000,
  })
}

/**
 * Текущий пользователь.
 *
 * Под защищённым маршрутом данные уже лежат в кэше — их положил `beforeLoad`
 * до первой отрисовки. `undefined` возможен только в момент выхода.
 */
export function useSession(): Me | undefined {
  return useQuery(sessionQueryOptions()).data
}

/** Разрешено ли этому способу аутентификации менять данные. */
export function canWrite(session: Me | undefined): boolean {
  return session?.scopes.includes('write') ?? false
}

export function useLogout() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: () => apiFetch<void>('/auth/logout', { method: 'POST' }),
    // `onSettled`, а не `onSuccess`: если сервер не ответил, человек всё равно
    // нажал «Выйти» — оставлять его внутри приложения нельзя.
    onSettled: async () => {
      await navigate({ to: '/login' })
      queryClient.clear()
    },
  })
}
