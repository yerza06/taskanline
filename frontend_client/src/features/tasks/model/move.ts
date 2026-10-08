import { arrayMove } from '@dnd-kit/sortable'

import type { MoveRequest } from '@/features/tasks/api/tasks'
import type { TaskGroup, TaskMove, TaskRead } from '@/shared/api/types'

export interface DndRules {
  /** Можно ли менять порядок внутри группы — только при ручной сортировке. */
  reorder: boolean
  /** Можно ли переносить между группами — только при группировке по статусу. */
  acrossGroups: boolean
}

/** Где задача окажется после броска: сосед для `move` и, если группа сменилась, статус. */
export function planMove(
  groups: TaskGroup[],
  activeId: string,
  fromGroup: string | null,
  toGroup: string | null,
  overTaskId: string | null,
  rules: DndRules,
): MoveRequest | null {
  const source = groups.find((group) => group.key === fromGroup)
  const target = groups.find((group) => group.key === toGroup)
  const task = source?.items.find((item) => item.id === activeId)
  if (!source || !target || !task) return null
  const changesGroup = fromGroup !== toGroup
  if (changesGroup && !rules.acrossGroups) return null

  let arranged: TaskRead[]
  if (changesGroup) {
    const rest = target.items
    const at = overTaskId ? rest.findIndex((item) => item.id === overTaskId) : -1
    arranged = [...rest]
    arranged.splice(at < 0 ? rest.length : at, 0, task)
  } else {
    const from = source.items.findIndex((item) => item.id === activeId)
    const to = overTaskId ? source.items.findIndex((item) => item.id === overTaskId) : source.items.length - 1
    if (from === to || to < 0) return null
    arranged = arrayMove(source.items, from, to)
  }

  const index = arranged.findIndex((item) => item.id === activeId)
  const move: TaskMove = {}
  if (changesGroup && toGroup) move.state_id = toGroup
  if (rules.reorder) {
    const before = arranged[index - 1]
    const after = arranged[index + 1]
    if (before) move.after_id = before.id
    else if (after) move.before_id = after.id
  }
  if (Object.keys(move).length === 0) return null
  return { task, toGroup, index, move }
}

