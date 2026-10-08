import type { Filters } from '@/shared/api/types'

type Kind = 'ids' | 'stateType' | 'priority' | 'date' | 'text' | 'bool'

export interface FieldSpec {
  label: string
  kind: Kind
  ops: string[]
}

export const FIELDS: Record<string, FieldSpec> = {
  team_id: { label: 'Команда', kind: 'ids', ops: ['in', 'nin'] },
  project_id: { label: 'Проект', kind: 'ids', ops: ['in', 'nin', 'is_null', 'not_null'] },
  state_id: { label: 'Статус', kind: 'ids', ops: ['in', 'nin'] },
  state_type: { label: 'Тип статуса', kind: 'stateType', ops: ['in', 'nin'] },
  assignee_id: { label: 'Исполнитель', kind: 'ids', ops: ['in', 'nin', 'is_null', 'not_null'] },
  creator_id: { label: 'Автор', kind: 'ids', ops: ['in', 'nin'] },
  label_id: { label: 'Метка', kind: 'ids', ops: ['in', 'nin'] },
  priority: { label: 'Приоритет', kind: 'priority', ops: ['in', 'lte', 'gte'] },
  due_date: { label: 'Срок', kind: 'date', ops: ['lt', 'lte', 'eq', 'gte', 'gt', 'is_null', 'not_null'] },
  created_at: { label: 'Создана', kind: 'date', ops: ['lt', 'lte', 'eq', 'gte', 'gt'] },
  updated_at: { label: 'Изменена', kind: 'date', ops: ['lt', 'lte', 'eq', 'gte', 'gt'] },
  title: { label: 'Название', kind: 'text', ops: ['contains'] },
  has_parent: { label: 'Подзадача', kind: 'bool', ops: ['eq'] },
  is_blocked: { label: 'Заблокирована', kind: 'bool', ops: ['eq'] },
}

/** Неполные условия (пустой список, пустая строка) не уходят на сервер — он бы их отверг. */
export function completeFilters(filters: Filters): Filters {
  return Object.fromEntries(
    Object.entries(filters).filter(([, condition]) => {
      if (condition.op === 'is_null' || condition.op === 'not_null') return true
      if (Array.isArray(condition.value)) return condition.value.length > 0
      if (typeof condition.value === 'string') return condition.value.trim().length > 0
      return condition.value !== undefined
    }),
  )
}

