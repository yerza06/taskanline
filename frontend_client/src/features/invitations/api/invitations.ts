import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'

import { SESSION_KEY } from '@/features/auth/api/session'
import { apiFetch, markSessionActive } from '@/shared/api/client'
import type { InvitationAccept, InvitationAccepted, InvitationPreview } from '@/shared/api/types'

function tokenPath(token: string): string {
  return `/invitations/token/${encodeURIComponent(token)}`
}

export function invitationPreviewQueryOptions(token: string) {
  return queryOptions({
    queryKey: ['invitation', token] as const,
    queryFn: () => apiFetch<InvitationPreview>(tokenPath(token)),
  })
}

/**
 * Принятие приглашения.
 *
 * С сессией тело не нужно; без неё — имя и пароль новой учётной записи, и
 * ответ приходит уже с cookie сессии, как после регистрации.
 */
export function useAcceptInvitation(token: string) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: (body?: InvitationAccept) =>
      apiFetch<InvitationAccepted>(`${tokenPath(token)}/accept`, { method: 'POST', json: body }),
    onSuccess: async () => {
      markSessionActive()
      // Членства изменились, а у нового человека сессия только что появилась.
      queryClient.removeQueries({ queryKey: SESSION_KEY })
      // Приглашение — это членство: корень приведёт в пространство, куда позвали.
      await navigate({ to: '/' })
    },
  })
}
