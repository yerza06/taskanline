import { useMutation, useQueryClient } from '@tanstack/react-query'

import { SESSION_KEY } from '@/features/auth/api/session'
import { apiFetch } from '@/shared/api/client'
import type { Me, UserUpdate } from '@/shared/api/types'

/**
 * Правка своего профиля.
 *
 * Ответ кладётся в кэш сессии целиком — шапка показывает новое имя сразу и без
 * второго запроса (архитектура §4.5).
 */
export function useUpdateProfile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (values: UserUpdate) => apiFetch<Me>('/me', { method: 'PATCH', json: values }),
    onSuccess: (updated) => {
      queryClient.setQueryData(SESSION_KEY, updated)
    },
  })
}
