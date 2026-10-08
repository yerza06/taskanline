import { describe, expect, it } from 'vitest'

import { planMove } from '@/features/tasks/model/move'
import type { TaskGroup } from '@/shared/api/types'
import { makeTask, STATES } from '@/test/msw/world'

const TODO = STATES[0]!.id
const DOING = STATES[1]!.id

function groups(): TaskGroup[] {
  const a = makeTask(1, 'A')
  const b = makeTask(2, 'B')
  const c = makeTask(3, 'C')
  const d = makeTask(4, 'D', { state_id: DOING })
  return [
    { key: TODO, count: 3, items: [a, b, c], next_cursor: null, has_more: false },
    { key: DOING, count: 1, items: [d], next_cursor: null, has_more: false },
  ]
}

const id = (n: number) => makeTask(n, '').id
const manual = { reorder: true, acrossGroups: true }

describe('куда ляжет задача после перетаскивания', () => {
  it('вниз внутри группы — после соседа сверху', () => {
    const plan = planMove(groups(), id(1), TODO, TODO, id(3), manual)

    expect(plan?.move).toEqual({ after_id: id(3) })
    expect(plan?.index).toBe(2)
  })

  it('в начало группы — перед первым', () => {
    const plan = planMove(groups(), id(3), TODO, TODO, id(1), manual)

    expect(plan?.move).toEqual({ before_id: id(1) })
  })

  it('в другую колонку — со сменой статуса и местом', () => {
    const plan = planMove(groups(), id(2), TODO, DOING, id(4), manual)

    expect(plan?.move).toEqual({ state_id: DOING, before_id: id(4) })
    expect(plan?.toGroup).toBe(DOING)
  })

  it('в пустое место колонки — в конец', () => {
    const plan = planMove(groups(), id(1), TODO, DOING, null, manual)

    expect(plan?.move).toEqual({ state_id: DOING, after_id: id(4) })
  })

  it('без ручной сортировки меняется только статус', () => {
    const plan = planMove(groups(), id(1), TODO, DOING, null, { reorder: false, acrossGroups: true })

    expect(plan?.move).toEqual({ state_id: DOING })
  })

  it('на своё же место — ничего', () => {
    expect(planMove(groups(), id(2), TODO, TODO, id(2), manual)).toBeNull()
  })

  it('между группами не по статусу — нельзя', () => {
    expect(planMove(groups(), id(1), TODO, DOING, null, { reorder: true, acrossGroups: false })).toBeNull()
  })
})
