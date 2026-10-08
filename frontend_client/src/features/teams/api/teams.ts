import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { SESSION_KEY } from '@/features/auth/api/session'
import { apiFetch } from '@/shared/api/client'
import type {
  LabelCreate,
  LabelRead,
  StateCreate,
  StateRead,
  StateUpdate,
  TeamCreate,
  TeamRead,
} from '@/shared/api/types'

export const teamsKey = (workspaceId: string) => ['workspace', workspaceId, 'teams'] as const
export const statesKey = (teamId: string) => ['team', teamId, 'states'] as const
export const labelsKey = (workspaceId: string) => ['workspace', workspaceId, 'labels'] as const

export function teamsQueryOptions(workspaceId: string) {
  return queryOptions({
    queryKey: teamsKey(workspaceId),
    queryFn: () => apiFetch<{ items: TeamRead[] }>(`/workspaces/${workspaceId}/teams`),
    select: (data) => data.items,
  })
}

export function useTeams(workspaceId: string | undefined) {
  return useQuery({ ...teamsQueryOptions(workspaceId ?? ''), enabled: Boolean(workspaceId) })
}

/** Команда по ключу из адреса (`ENG`). */
export function useTeamByKey(workspaceId: string | undefined, key: string | undefined) {
  const teams = useTeams(workspaceId).data
  return teams?.find((team) => team.key === key?.toUpperCase())
}

export function useCreateTeam(workspaceId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (values: TeamCreate) =>
      apiFetch<TeamRead>(`/workspaces/${workspaceId}/teams`, { method: 'POST', json: values }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: teamsKey(workspaceId) }),
        queryClient.invalidateQueries({ queryKey: SESSION_KEY }),
      ])
    },
  })
}

// --- Статусы -------------------------------------------------------------------

export function statesQueryOptions(teamId: string) {
  return queryOptions({
    queryKey: statesKey(teamId),
    queryFn: () => apiFetch<{ items: StateRead[] }>(`/teams/${teamId}/states`),
    // Порядок колонок доски и пунктов меню — позиция, а не порядок ответа.
    select: (data) => [...data.items].sort((a, b) => a.position - b.position),
    staleTime: 5 * 60_000,
  })
}

export function useStates(teamId: string | undefined) {
  return useQuery({ ...statesQueryOptions(teamId ?? ''), enabled: Boolean(teamId) })
}

function useStateMutation<T>(teamId: string, fn: (values: T) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: statesKey(teamId) })
    },
  })
}

export function useCreateState(teamId: string) {
  return useStateMutation(teamId, (values: StateCreate) =>
    apiFetch<StateRead>(`/teams/${teamId}/states`, { method: 'POST', json: values }),
  )
}

export function useUpdateState(teamId: string) {
  return useStateMutation(teamId, ({ id, ...values }: StateUpdate & { id: string }) =>
    apiFetch<StateRead>(`/states/${id}`, { method: 'PATCH', json: values }),
  )
}

export function useDeleteState(teamId: string) {
  return useStateMutation(teamId, ({ id, moveTo }: { id: string; moveTo?: string }) =>
    apiFetch<void>(`/states/${id}${moveTo ? `?move_to=${moveTo}` : ''}`, { method: 'DELETE' }),
  )
}

// --- Метки ---------------------------------------------------------------------

export function labelsQueryOptions(workspaceId: string) {
  return queryOptions({
    queryKey: labelsKey(workspaceId),
    queryFn: () => apiFetch<{ items: LabelRead[] }>(`/labels?workspace_id=${workspaceId}`),
    select: (data) => data.items,
    staleTime: 5 * 60_000,
  })
}

/** Метки, доступные задачам команды: общие для workspace и метки самой команды. */
export function useLabels(workspaceId: string | undefined, teamId?: string) {
  return useQuery({
    ...labelsQueryOptions(workspaceId ?? ''),
    enabled: Boolean(workspaceId),
    select: (data) =>
      data.items.filter((label) => !teamId || label.team_id === null || label.team_id === teamId),
  })
}

function useLabelMutation<T>(workspaceId: string, fn: (values: T) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: labelsKey(workspaceId) })
    },
  })
}

export function useCreateLabel(workspaceId: string) {
  return useLabelMutation(workspaceId, (values: Omit<LabelCreate, 'workspace_id'>) =>
    apiFetch<LabelRead>('/labels', {
      method: 'POST',
      json: { ...values, workspace_id: workspaceId },
    }),
  )
}

export function useDeleteLabel(workspaceId: string) {
  return useLabelMutation(workspaceId, (id: string) =>
    apiFetch<void>(`/labels/${id}`, { method: 'DELETE' }),
  )
}
