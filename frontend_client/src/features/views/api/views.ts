import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from '@/shared/api/client'
import type { ViewCreate, ViewRead, ViewUpdate } from '@/shared/api/types'

export const viewsKey = (workspaceId: string) => ['workspace', workspaceId, 'views'] as const
export const viewKey = (viewId: string) => ['view', viewId] as const

export function viewsQueryOptions(workspaceId: string) {
  return queryOptions({
    queryKey: viewsKey(workspaceId),
    queryFn: () => apiFetch<{ items: ViewRead[] }>(`/views?workspace_id=${workspaceId}`),
    select: (data) => data.items,
  })
}

export function useViews(workspaceId: string | undefined) {
  return useQuery({ ...viewsQueryOptions(workspaceId ?? ''), enabled: Boolean(workspaceId) })
}

export function useView(viewId: string) {
  return useQuery({
    queryKey: viewKey(viewId),
    queryFn: () => apiFetch<ViewRead>(`/views/${viewId}`),
  })
}

export function useCreateView(workspaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: Omit<ViewCreate, 'workspace_id'>) =>
      apiFetch<ViewRead>('/views', {
        method: 'POST',
        json: { ...values, workspace_id: workspaceId },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: viewsKey(workspaceId) })
    },
  })
}

export function useUpdateView(workspaceId: string, viewId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: ViewUpdate) =>
      apiFetch<ViewRead>(`/views/${viewId}`, { method: 'PATCH', json: values }),
    onSuccess: async (view) => {
      queryClient.setQueryData(viewKey(viewId), view)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: viewsKey(workspaceId) }),
        queryClient.invalidateQueries({ queryKey: ['tasks', 'view', viewId] }),
      ])
    },
  })
}

export function useDeleteView(workspaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (viewId: string) => apiFetch<void>(`/views/${viewId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: viewsKey(workspaceId) })
    },
  })
}
