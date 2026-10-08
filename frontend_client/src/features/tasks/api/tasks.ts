import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'

import { apiFetch } from '@/shared/api/client'
import type {
  ActivityRead,
  CommentRead,
  Filters,
  QueryTasks,
  RelationCreate,
  RelationRead,
  SortDirection,
  TaskCreate,
  TaskGroup,
  TaskMove,
  TaskRead,
  TaskUpdate,
  ViewGroupBy,
  ViewSortBy,
} from '@/shared/api/types'

/** Всё, что нужно строке списка и карточке доски, — одним запросом. */
export const LIST_EXPAND = 'state,assignee,labels,project'
const DETAIL_EXPAND = 'state,assignee,creator,labels,project,parent,relations'

/**
 * Префикс всех списков задач. Мутация задачи инвалидирует его целиком: задача могла
 * уйти из одного среза и появиться в другом, и угадывать, в каких именно, дороже,
 * чем переспросить открытые.
 */
export const TASK_LISTS_KEY = ['tasks'] as const
export const taskKey = (ref: string) => ['task', ref.toUpperCase()] as const

export interface TaskQueryParams {
  workspaceId: string
  filters: Filters
  sortBy: ViewSortBy
  sortDirection: SortDirection
  groupBy: ViewGroupBy | null
  limit?: number
}

export function taskQueryOptions(params: TaskQueryParams) {
  return queryOptions({
    queryKey: [...TASK_LISTS_KEY, 'query', params] as const,
    queryFn: () =>
      apiFetch<QueryTasks>(`/views/query?expand=${LIST_EXPAND}`, {
        method: 'POST',
        json: {
          workspace_id: params.workspaceId,
          filters: params.filters,
          sort_by: params.sortBy,
          sort_direction: params.sortDirection,
          group_by: params.groupBy,
          limit: params.limit ?? 100,
        },
      }),
    // Без realtime открытый список подтягивает чужие изменения раз в минуту (§4.5).
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
  })
}

export function useTaskQuery(params: TaskQueryParams | null) {
  return useQuery({
    ...taskQueryOptions(params ?? ({} as TaskQueryParams)),
    enabled: params !== null,
  })
}

export function viewTasksQueryOptions(viewId: string) {
  return queryOptions({
    queryKey: [...TASK_LISTS_KEY, 'view', viewId] as const,
    queryFn: () =>
      apiFetch<QueryTasks>(`/views/${viewId}/tasks?expand=${LIST_EXPAND}&limit=100`),
    refetchInterval: 60_000,
  })
}

export function useTask(ref: string) {
  return useQuery({
    queryKey: taskKey(ref),
    queryFn: () => apiFetch<TaskRead>(`/tasks/${encodeURIComponent(ref)}?expand=${DETAIL_EXPAND}`),
  })
}

export function useSubtasks(taskId: string | undefined) {
  return useQuery({
    queryKey: ['task', taskId, 'subtasks'],
    queryFn: () =>
      apiFetch<{ items: TaskRead[] }>(`/tasks/${taskId}/subtasks?expand=${LIST_EXPAND}`),
    select: (data) => data.items,
    enabled: Boolean(taskId),
  })
}

export function useComments(taskId: string | undefined) {
  return useQuery({
    queryKey: ['task', taskId, 'comments'],
    queryFn: () => apiFetch<{ items: CommentRead[] }>(`/tasks/${taskId}/comments?limit=100`),
    select: (data) => data.items,
    enabled: Boolean(taskId),
  })
}

export function useActivities(taskId: string | undefined) {
  return useQuery({
    queryKey: ['task', taskId, 'activities'],
    queryFn: () => apiFetch<{ items: ActivityRead[] }>(`/tasks/${taskId}/activities?limit=50`),
    select: (data) => data.items,
    enabled: Boolean(taskId),
  })
}

/** Ответ мутации — задача целиком: она ложится в кэш карточки без второго запроса (§4.5). */
async function settle(queryClient: QueryClient, task: TaskRead): Promise<void> {
  const current = queryClient.getQueryData<TaskRead>(taskKey(task.key))
  queryClient.setQueryData(taskKey(task.key), { ...current, ...task })
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: TASK_LISTS_KEY }),
    queryClient.invalidateQueries({ queryKey: ['task', task.id] }),
    queryClient.invalidateQueries({ queryKey: taskKey(task.key) }),
  ])
}

export function useCreateTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: TaskCreate) =>
      apiFetch<TaskRead>(`/tasks?expand=${LIST_EXPAND}`, {
        method: 'POST',
        json: values,
        // Повтор после обрыва сети вернёт ту же задачу, а не создаст вторую.
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      }),
    onSuccess: async (task) => {
      await settle(queryClient, task)
      if (task.parent_id) {
        await queryClient.invalidateQueries({ queryKey: ['task', task.parent_id, 'subtasks'] })
      }
    },
  })
}

export function useUpdateTask(task: Pick<TaskRead, 'id' | 'key'>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: TaskUpdate) =>
      apiFetch<TaskRead>(`/tasks/${task.id}?expand=${DETAIL_EXPAND}`, {
        method: 'PATCH',
        json: changes,
      }),
    // Оптимистично: поле меняется сразу, а при отказе сервера возвращается как было.
    onMutate: async (changes) => {
      await queryClient.cancelQueries({ queryKey: taskKey(task.key) })
      const previous = queryClient.getQueryData<TaskRead>(taskKey(task.key))
      if (previous) {
        queryClient.setQueryData(taskKey(task.key), { ...previous, ...changes })
      }
      return { previous }
    },
    onError: (_error, _changes, context) => {
      if (context?.previous) {
        queryClient.setQueryData(taskKey(task.key), context.previous)
      }
    },
    onSuccess: (updated) => settle(queryClient, updated),
  })
}

export function useSetLabels(task: Pick<TaskRead, 'id' | 'key'>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (labelIds: string[]) =>
      apiFetch<TaskRead>(`/tasks/${task.id}/labels`, {
        method: 'PUT',
        json: { label_ids: labelIds },
      }),
    onSuccess: (updated) => settle(queryClient, updated),
  })
}

export function useDeleteTask(task: Pick<TaskRead, 'id' | 'key'>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiFetch<void>(`/tasks/${task.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: taskKey(task.key) })
      await queryClient.invalidateQueries({ queryKey: TASK_LISTS_KEY })
    },
  })
}

export function useAddComment(taskId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: string) =>
      apiFetch<CommentRead>(`/tasks/${taskId}/comments`, { method: 'POST', json: { body } }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['task', taskId, 'comments'] }),
        queryClient.invalidateQueries({ queryKey: ['task', taskId, 'activities'] }),
      ])
    },
  })
}

export function useAddRelation(task: Pick<TaskRead, 'id' | 'key'>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: RelationCreate) =>
      apiFetch<RelationRead>(`/tasks/${task.id}/relations`, { method: 'POST', json: values }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: taskKey(task.key) })
    },
  })
}

export function useRemoveRelation(task: Pick<TaskRead, 'id' | 'key'>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (relationId: string) =>
      apiFetch<void>(`/tasks/${task.id}/relations/${relationId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: taskKey(task.key) })
    },
  })
}

// --- Перестановка ------------------------------------------------------------------

export interface MoveRequest {
  task: TaskRead
  /** Группа, куда кладётся задача (ключ из ответа, `null` — без группировки). */
  toGroup: string | null
  /** Позиция в целевой группе после перестановки. */
  index: number
  move: TaskMove
}

/**
 * Положить задачу в группу `toGroup` на место `index` — чистая функция над ответом
 * списка. Ей пользуется оптимистичное обновление: доска перестраивается сразу, а не
 * после ответа сервера.
 */
export function moveInGroups(
  groups: TaskGroup[],
  taskId: string,
  toGroup: string | null,
  index: number,
  patch: Partial<TaskRead> = {},
): TaskGroup[] {
  let moved: TaskRead | undefined
  const without = groups.map((group) => {
    const found = group.items.find((item) => item.id === taskId)
    if (!found) return group
    moved = found
    return { ...group, count: group.count - 1, items: group.items.filter((i) => i.id !== taskId) }
  })
  if (!moved) return groups
  const placed = { ...moved, ...patch }
  return without.map((group) => {
    if (group.key !== toGroup) return group
    const items = [...group.items]
    items.splice(Math.max(0, Math.min(index, items.length)), 0, placed)
    return { ...group, count: group.count + 1, items }
  })
}

export function useMoveTask(listKey: readonly unknown[]) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ task, move }: MoveRequest) =>
      apiFetch<TaskRead>(`/tasks/${task.id}/move`, { method: 'POST', json: move }),
    onMutate: async ({ task, toGroup, index, move }) => {
      await queryClient.cancelQueries({ queryKey: listKey })
      const previous = queryClient.getQueryData<QueryTasks>(listKey)
      if (previous) {
        const patch = move.state_id ? { state_id: move.state_id } : {}
        queryClient.setQueryData<QueryTasks>(listKey, {
          ...previous,
          groups: moveInGroups(previous.groups, task.id, toGroup, index, patch),
        })
      }
      return { previous }
    },
    onError: (_error, _request, context) => {
      if (context?.previous) {
        queryClient.setQueryData(listKey, context.previous)
      }
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: TASK_LISTS_KEY })
    },
  })
}
