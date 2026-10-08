import { DroppableGroup, SortableTask, TaskDnd } from '@/features/tasks/components/TaskDnd'
import type { DndRules } from '@/features/tasks/model/move'
import { TaskCard } from '@/features/tasks/components/TaskItems'
import type { MoveRequest } from '@/features/tasks/api/tasks'
import type { TaskGroup } from '@/shared/api/types'

/**
 * Доска: колонка на группу. Колонки прокручиваются вбок, на телефоне — по одной
 * колонке почти во всю ширину экрана.
 */
export function TaskBoard({
  workspace,
  columns,
  title,
  rules,
  onMove,
}: {
  workspace: string
  columns: TaskGroup[]
  title: (group: TaskGroup) => string
  rules: DndRules
  onMove: (request: MoveRequest) => void
}) {
  return (
    <TaskDnd
      groups={columns}
      rules={rules}
      onMove={onMove}
      renderOverlay={(task) => <TaskCard workspace={workspace} task={task} className="w-72 shadow-lg" />}
    >
      <div className="flex h-full gap-3 overflow-x-auto p-3">
        {columns.map((column) => (
          <section
            key={column.key ?? 'none'}
            aria-label={title(column)}
            className="bg-surface-hover/40 border-border flex w-[85vw] max-w-72 shrink-0 flex-col rounded-lg border sm:w-72"
          >
            <h2 className="flex items-center gap-2 px-3 py-2 text-sm font-semibold">
              {title(column)}
              <span className="text-fg-muted font-normal">{column.count}</span>
            </h2>
            <DroppableGroup group={column} className="flex min-h-24 flex-1 flex-col gap-2 rounded-b-lg p-2">
              {column.items.map((task) => (
                <SortableTask key={task.id} task={task} group={column.key} disabled={false}>
                  {(handle) => <TaskCard workspace={workspace} task={task} handle={handle} />}
                </SortableTask>
              ))}
            </DroppableGroup>
          </section>
        ))}
      </div>
    </TaskDnd>
  )
}
