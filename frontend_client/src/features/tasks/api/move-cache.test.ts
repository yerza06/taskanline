import { describe, expect, it } from 'vitest'

import { moveInGroups } from '@/features/tasks/api/tasks'
import type { TaskGroup } from '@/shared/api/types'
import { makeTask, STATES } from '@/test/msw/world'

describe('оптимистичная перестановка в кэше', () => {
  it('переносит задачу между группами и пересчитывает счётчики', () => {
    const a = makeTask(1, 'A')
    const b = makeTask(2, 'B', { state_id: STATES[1]!.id })
    const groups: TaskGroup[] = [
      { key: STATES[0]!.id, count: 1, items: [a], next_cursor: null, has_more: false },
      { key: STATES[1]!.id, count: 1, items: [b], next_cursor: null, has_more: false },
    ]

    const result = moveInGroups(groups, a.id, STATES[1]!.id, 0, { state_id: STATES[1]!.id })

    expect(result.map((g) => [g.count, g.items.map((t) => t.key)])).toEqual([
      [0, []],
      [2, ['ENG-1', 'ENG-2']],
    ])
    expect(result[1]!.items[0]!.state_id).toBe(STATES[1]!.id)
  })
})
