import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import type { MoveRequest } from '@/features/tasks/api/tasks'
import { planMove, type DndRules } from '@/features/tasks/model/move'
import type { TaskGroup, TaskRead } from '@/shared/api/types'
import { cn } from '@/shared/lib/cn'

/**
 * Перетаскивание задач между группами и внутри них — для списка и доски.
 *
 * Работает и мышью, и клавиатурой: фокус на задаче, пробел — взять, стрелки —
 * двигать (влево-вправо между колонками доски), пробел — положить, Escape —
 * отменить. Скринридер слышит каждое действие по-русски.
 */

const groupId = (key: string | null) => `group:${key ?? '∅'}`

interface DragData {
  group: string | null
  task?: TaskRead
}

const announcements = (title: (id: string) => string): Announcements => ({
  onDragStart: ({ active }) => `Взята задача ${title(String(active.id))}.`,
  onDragOver: ({ active, over }) =>
    over ? `Задача ${title(String(active.id))} над новым местом.` : 'Задача вне списка.',
  onDragEnd: ({ active, over }) =>
    over ? `Задача ${title(String(active.id))} перемещена.` : 'Перемещение отменено.',
  onDragCancel: ({ active }) => `Перемещение задачи ${title(String(active.id))} отменено.`,
})

export function TaskDnd({
  groups,
  rules,
  onMove,
  renderOverlay,
  children,
}: {
  groups: TaskGroup[]
  rules: DndRules
  onMove: (request: MoveRequest) => void
  renderOverlay: (task: TaskRead) => ReactNode
  children: ReactNode
}) {
  const [active, setActive] = useState<TaskRead | null>(null)
  const sensors = useSensors(
    // Порог в 5px: щелчок по ссылке задачи не превращается в перетаскивание.
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const titles = new Map(groups.flatMap((g) => g.items.map((t) => [t.id, `${t.key} «${t.title}»`])))

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      accessibility={{
        announcements: announcements((id) => titles.get(id) ?? ''),
        screenReaderInstructions: {
          draggable:
            'Чтобы переместить задачу, нажмите пробел, двигайте стрелками и нажмите пробел ещё раз. Escape — отмена.',
        },
      }}
      onDragStart={(event: DragStartEvent) => {
        setActive((event.active.data.current as DragData | undefined)?.task ?? null)
      }}
      onDragCancel={() => setActive(null)}
      onDragEnd={(event: DragEndEvent) => {
        setActive(null)
        const from = event.active.data.current as DragData | undefined
        const over = event.over?.data.current as DragData | undefined
        if (!from || !over || !event.over) return
        const overTask = over.task ? String(event.over.id) : null
        const plan = planMove(groups, String(event.active.id), from.group, over.group, overTask, rules)
        if (plan) onMove(plan)
      }}
    >
      {children}
      <DragOverlay>{active ? renderOverlay(active) : null}</DragOverlay>
    </DndContext>
  )
}

/** Группа — место, куда можно бросить задачу, даже пустая. */
export function DroppableGroup({
  group,
  className,
  children,
}: {
  group: TaskGroup
  className?: string
  children: ReactNode
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: groupId(group.key),
    data: { group: group.key } satisfies DragData,
  })
  return (
    <div ref={setNodeRef} className={cn(className, isOver && 'outline-fg outline-2 -outline-offset-2')}>
      <SortableContext items={group.items.map((task) => task.id)} strategy={verticalListSortingStrategy}>
        {children}
      </SortableContext>
    </div>
  )
}

/**
 * Задача, которую можно перетащить. Тащится за отдельную ручку-кнопку, а не за
 * всю строку: строка содержит ссылку на задачу, и кнопка вокруг ссылки сломала
 * бы и клавиатуру, и скринридер.
 */
export function SortableTask({
  task,
  group,
  disabled,
  children,
}: {
  task: TaskRead
  group: string | null
  disabled: boolean
  children: (handle: ReactNode) => ReactNode
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id: task.id, data: { group, task } satisfies DragData, disabled })
  const handle = disabled ? null : (
    <button
      type="button"
      ref={setActivatorNodeRef}
      {...attributes}
      {...listeners}
      aria-roledescription="перемещаемая задача"
      aria-label={`Переместить ${task.key}`}
      className="text-fg-muted hover:text-fg focus-visible:outline-accent cursor-grab touch-none rounded p-0.5 focus-visible:outline-2"
    >
      <GripVertical aria-hidden="true" className="size-4" />
    </button>
  )
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(isDragging && 'opacity-40')}
    >
      {children(handle)}
    </div>
  )
}
