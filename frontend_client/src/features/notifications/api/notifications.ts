import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from '@/shared/api/client'
import type { NotificationRead } from '@/shared/api/types'

export const NOTIFICATIONS_KEY = ['notifications'] as const

interface NotificationPage {
  items: NotificationRead[]
  next_cursor: string | null
  has_more: boolean
}

export function useNotifications({ unread = false }: { unread?: boolean } = {}) {
  return useQuery({
    queryKey: [...NOTIFICATIONS_KEY, { unread }],
    queryFn: () =>
      apiFetch<NotificationPage>(`/me/notifications?limit=50${unread ? '&unread=true' : ''}`),
    // Счётчик в меню — единственный «живой» элемент без realtime: опрос раз в минуту.
    refetchInterval: 60_000,
  })
}

export function useMarkRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<NotificationRead>(`/me/notifications/${id}/read`, { method: 'POST' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY })
    },
  })
}
