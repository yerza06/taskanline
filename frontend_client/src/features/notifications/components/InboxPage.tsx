import { Link } from '@tanstack/react-router'
import { useState } from 'react'

import { useMembers } from '@/features/members/api/members'
import { useMarkRead, useNotifications } from '@/features/notifications/api/notifications'
import { NOTIFICATION_LABELS } from '@/features/tasks/model/labels'
import { useCurrentWorkspace } from '@/features/workspaces/api/workspaces'
import { apiFetch } from '@/shared/api/client'
import type { TaskRead } from '@/shared/api/types'
import { formatDateTime } from '@/shared/lib/format'
import { cn } from '@/shared/lib/cn'
import { useQueries } from '@tanstack/react-query'

/** Лента уведомлений: упоминания, назначения, комментарии и смены статуса. */
export function InboxPage() {
  const workspace = useCurrentWorkspace()
  const [unread, setUnread] = useState(false)
  const feed = useNotifications({ unread })
  const markRead = useMarkRead()
  const members = useMembers('workspace', workspace?.id).data ?? []
  const items = (feed.data?.items ?? []).filter((item) => item.workspace_id === workspace?.id)
  // Ключ и название задачи — по id из уведомления; задачи кэшируются, повторов нет.
  const taskIds = [...new Set(items.map((item) => item.task_id).filter((id): id is string => Boolean(id)))]
  const tasks = useQueries({
    queries: taskIds.map((id) => ({
      queryKey: ['task-brief', id],
      queryFn: () => apiFetch<TaskRead>(`/tasks/${id}`),
      staleTime: 5 * 60_000,
      retry: false,
    })),
  })
  const byId = new Map(tasks.flatMap((result) => (result.data ? [[result.data.id, result.data]] : [])))

  if (!workspace) return null
  return (
    <div className="mx-auto w-full max-w-3xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-display flex-1 text-2xl font-semibold tracking-tight">Входящие</h1>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={unread} onChange={(e) => setUnread(e.target.checked)} />
          Только непрочитанные
        </label>
      </div>
      {items.length === 0 && feed.isSuccess && <p className="text-fg-muted text-sm">Уведомлений нет.</p>}
      <ul className="divide-border border-border divide-y rounded-md border">
        {items.map((item) => {
          const task = item.task_id ? byId.get(item.task_id) : undefined
          const actor = members.find((m) => m.user_id === item.actor_id)?.full_name ?? 'Кто-то'
          return (
            <li
              key={item.id}
              className={cn('flex flex-wrap items-center gap-3 px-3 py-2 text-sm', !item.read_at && 'font-semibold')}
            >
              {!item.read_at && <span className="bg-fg size-2 shrink-0 rounded-full" aria-label="Не прочитано" />}
              <span className="min-w-0 flex-1">
                {actor} {NOTIFICATION_LABELS[item.type]}
                {task && (
                  <>
                    {' '}
                    <Link
                      to="/w/$workspace/task/$key"
                      params={{ workspace: workspace.slug, key: task.key }}
                      className="underline-offset-2 hover:underline"
                      onClick={() => !item.read_at && markRead.mutate(item.id)}
                    >
                      {task.key} {task.title}
                    </Link>
                  </>
                )}
              </span>
              <span className="text-fg-muted text-xs font-normal">{formatDateTime(item.created_at)}</span>
              {!item.read_at && (
                <button
                  type="button"
                  className="text-fg-muted hover:text-fg text-xs font-normal underline"
                  onClick={() => markRead.mutate(item.id)}
                >
                  Прочитано
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
