import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from '@/shared/api/client'
import type { InvitationCreate, InvitationRead, InvitationScope } from '@/shared/api/types'

/** Уровень членства: workspace, команда или проект — у всех трёх одинаковые маршруты. */
export type MemberLevel = InvitationScope

export interface Member {
  user_id: string
  email: string
  full_name: string
  avatar_url: string | null
  joined_at: string
  role: string
}

const PATHS: Record<MemberLevel, string> = {
  workspace: 'workspaces',
  team: 'teams',
  project: 'projects',
}

export const membersKey = (level: MemberLevel, id: string) => ['members', level, id] as const
export const invitationsKey = (workspaceId: string) => ['invitations', workspaceId] as const

export function membersQueryOptions(level: MemberLevel, id: string) {
  return queryOptions({
    queryKey: membersKey(level, id),
    queryFn: () => apiFetch<{ items: Member[] }>(`/${PATHS[level]}/${id}/members`),
    select: (data) => data.items,
  })
}

export function useMembers(level: MemberLevel, id: string | undefined) {
  return useQuery({ ...membersQueryOptions(level, id ?? ''), enabled: Boolean(id) })
}

export function useChangeRole(level: MemberLevel, id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      apiFetch<Member>(`/${PATHS[level]}/${id}/members/${userId}`, {
        method: 'PATCH',
        json: { role },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: membersKey(level, id) })
    },
  })
}

export function useRemoveMember(level: MemberLevel, id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) =>
      apiFetch<void>(`/${PATHS[level]}/${id}/members/${userId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: membersKey(level, id) })
    },
  })
}

export function useInvitations(workspaceId: string | undefined) {
  return useQuery({
    queryKey: invitationsKey(workspaceId ?? ''),
    queryFn: () =>
      apiFetch<{ items: InvitationRead[] }>(`/invitations?workspace_id=${workspaceId}`),
    select: (data) => data.items,
    enabled: Boolean(workspaceId),
  })
}

export function useInvite(workspaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: InvitationCreate) =>
      apiFetch<InvitationRead>('/invitations', { method: 'POST', json: values }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: invitationsKey(workspaceId) })
    },
  })
}

export function useRevokeInvitation(workspaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/invitations/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: invitationsKey(workspaceId) })
    },
  })
}
