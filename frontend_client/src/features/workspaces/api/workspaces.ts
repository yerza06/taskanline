import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from '@tanstack/react-router'

import { SESSION_KEY, useSession } from '@/features/auth/api/session'
import { apiFetch } from '@/shared/api/client'
import type { WorkspaceCreate, WorkspaceRead } from '@/shared/api/types'

export const WORKSPACES_KEY = ['workspaces'] as const

export function workspacesQueryOptions() {
  return queryOptions({
    queryKey: WORKSPACES_KEY,
    queryFn: () => apiFetch<{ items: WorkspaceRead[] }>('/workspaces'),
    staleTime: 5 * 60_000,
  })
}

export function useWorkspaces() {
  return useQuery({ ...workspacesQueryOptions(), select: (data) => data.items })
}

/**
 * Текущее пространство — по slug из адреса.
 *
 * Slug, а не id, стоит в адресе намеренно: ссылку `/w/acme/task/ENG-42` человек
 * читает и может переслать. Под маршрутом `/w/$workspace` пространство уже
 * проверено в `beforeLoad`, поэтому `undefined` здесь — только мгновение выхода.
 */
export function useCurrentWorkspace(): WorkspaceRead | undefined {
  const { workspace } = useParams({ strict: false })
  const spaces = useWorkspaces().data
  return spaces?.find((space) => space.slug === workspace)
}

/** Роль текущего пользователя в пространстве — по членствам из `/me`. */
export function useWorkspaceRole(workspaceId: string | undefined): string | undefined {
  const session = useSession()
  return session?.memberships.workspaces.find((m) => m.workspace_id === workspaceId)?.role
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (values: WorkspaceCreate) =>
      apiFetch<WorkspaceRead>('/workspaces', { method: 'POST', json: values }),
    onSuccess: async (space) => {
      // Сразу в кэш: следующий экран — само пространство, и его проверка в
      // `beforeLoad` не должна увидеть список без него.
      queryClient.setQueryData<{ items: WorkspaceRead[] }>(WORKSPACES_KEY, (old) => ({
        items: [...(old?.items ?? []), space],
      }))
      // Создатель становится владельцем: меняются и список, и членства в `/me`.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: WORKSPACES_KEY }),
        queryClient.invalidateQueries({ queryKey: SESSION_KEY }),
      ])
    },
  })
}
