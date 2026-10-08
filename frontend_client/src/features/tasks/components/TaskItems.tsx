import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'

import { formatDate } from '@/features/tasks/model/groups'
import { Avatar, PriorityIcon, StateIcon } from '@/features/tasks/components/TaskIcons'
import type { TaskRead } from '@/shared/api/types'
import { cn } from '@/shared/lib/cn'

function Labels({ task }: { task: TaskRead }) {
  if (!task.labels?.length) return null
  return (
    <span className="flex min-w-0 flex-wrap gap-1">
      {task.labels.map((label) => (
        <span
          key={label.id}
          className="border-border text-fg-muted rounded-full border px-1.5 text-[11px] leading-4"
        >
          {label.name}
        </span>
      ))}
    </span>
  )
}

function TaskLink({ workspace, task, className }: { workspace: string; task: TaskRead; className?: string }) {
  return (
    <Link
      to="/w/$workspace/task/$key"
      params={{ workspace, key: task.key }}
      className={cn('hover:underline focus-visible:outline-accent rounded focus-visible:outline-2', className)}
    >
      {task.title}
    </Link>
  )
}

/** Строка списка: всё главное в одну линию, на узком экране — в две. */
export function TaskRow({ workspace, task, handle }: { workspace: string; task: TaskRead; handle?: ReactNode }) {
  return (
    <div className="hover:bg-surface-hover flex min-h-10 flex-wrap items-center gap-x-3 gap-y-1 px-3 py-1.5 text-sm">
      {handle}
      <PriorityIcon priority={task.priority} />
      <span className="text-fg-muted w-16 shrink-0 font-mono text-xs">{task.key}</span>
      {task.state && <StateIcon type={task.state.type} />}
      <TaskLink workspace={workspace} task={task} className="min-w-0 flex-1 truncate" />
      <Labels task={task} />
      {task.due_date && (
        <span className="text-fg-muted shrink-0 text-xs">{formatDate(task.due_date)}</span>
      )}
      {task.assignee ? (
        <Avatar name={task.assignee.full_name} />
      ) : (
        <span className="text-fg-muted w-6 shrink-0 text-center text-xs" title="Без исполнителя">
          —
        </span>
      )}
    </div>
  )
}

/** Карточка доски. */
export function TaskCard({
  workspace,
  task,
  handle,
  className,
}: {
  workspace: string
  task: TaskRead
  handle?: ReactNode
  className?: string
}) {
  return (
    <article
      className={cn('border-border bg-surface space-y-2 rounded-md border p-2.5 text-sm shadow-xs', className)}
    >
      <div className="flex items-center gap-2">
        {handle}
        <span className="text-fg-muted font-mono text-xs">{task.key}</span>
        <PriorityIcon priority={task.priority} className="ml-auto" />
      </div>
      <TaskLink workspace={workspace} task={task} className="block leading-snug" />
      <div className="flex items-center gap-2">
        <Labels task={task} />
        {task.due_date && (
          <span className="text-fg-muted ml-auto text-xs">{formatDate(task.due_date)}</span>
        )}
        {task.assignee && <Avatar name={task.assignee.full_name} className={task.due_date ? '' : 'ml-auto'} />}
      </div>
    </article>
  )
}
