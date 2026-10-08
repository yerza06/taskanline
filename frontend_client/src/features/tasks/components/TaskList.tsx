import { DroppableGroup, SortableTask, TaskDnd } from '@/features/tasks/components/TaskDnd'
import type { DndRules } from '@/features/tasks/model/move'
import { TaskCard, TaskRow } from '@/features/tasks/components/TaskItems'
import type { MoveRequest } from '@/features/tasks/api/tasks'
import type { TaskGroup } from '@/shared/api/types'

export function TaskList({
  workspace,
  groups,
  title,
  rules,
  onMove,
}: {
  workspace: string
  groups: TaskGroup[]
  title: (group: TaskGroup) => string
  rules: DndRules
  onMove: (request: MoveRequest) => void
}) {
  const draggable = rules.reorder || rules.acrossGroups
  const single = groups.length === 1 && groups[0]?.key === null

  return (
    <TaskDnd
      groups={groups}
      rules={rules}
      onMove={onMove}
      renderOverlay={(task) => <TaskCard workspace={workspace} task={task} className="shadow-lg" />}
    >
      <div className="space-y-4">
        {groups.map((group) => (
          <section key={group.key ?? 'none'} aria-label={title(group)}>
            {!single && (
              <h2 className="border-border bg-canvas sticky top-0 z-10 flex items-center gap-2 border-b px-3 py-1.5 text-sm font-semibold">
                {title(group)}
                <span className="text-fg-muted font-normal">{group.count}</span>
              </h2>
            )}
            <DroppableGroup group={group} className="divide-border min-h-2 divide-y">
              {group.items.map((task) => (
                <SortableTask key={task.id} task={task} group={group.key} disabled={!draggable}>
                  {(handle) => <TaskRow workspace={workspace} task={task} handle={handle} />}
                </SortableTask>
              ))}
            </DroppableGroup>
            {group.has_more && (
              <p className="text-fg-muted px-3 py-2 text-xs">
                Показаны первые {group.items.length} из {group.count}. Уточните фильтр.
              </p>
            )}
          </section>
        ))}
      </div>
    </TaskDnd>
  )
}
