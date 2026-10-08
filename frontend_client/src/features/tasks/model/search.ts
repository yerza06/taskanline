import type { Filters, SortDirection, ViewGroupBy, ViewLayout, ViewSortBy } from '@/shared/api/types'

/**
 * Состояние среза задач в адресе: вид, группировка, сортировка и фильтры.
 *
 * В адресе, а не в памяти компонента: ссылку на «доску ENG, сгруппированную по
 * исполнителю, только баги» можно переслать, и кнопка «назад» возвращает прежний
 * срез (архитектура §4.1).
 */
export interface TaskSearch {
  layout?: ViewLayout
  group?: ViewGroupBy | 'none'
  sort?: ViewSortBy
  dir?: SortDirection
  filters?: Filters
}

const LAYOUTS: readonly ViewLayout[] = ['list', 'board']
const GROUPS: readonly (ViewGroupBy | 'none')[] = [
  'none',
  'state',
  'assignee',
  'priority',
  'project',
  'label',
  'due_date',
]
const SORTS: readonly ViewSortBy[] = [
  'manual',
  'priority',
  'due_date',
  'created_at',
  'updated_at',
  'title',
]

function pick<T extends string>(value: unknown, allowed: readonly T[]): T | undefined {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : undefined
}

/** Фильтры из адреса проверяются только по форме — содержимое проверит сервер. */
function filtersOf(value: unknown): Filters | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  const result: Filters = {}
  for (const [field, condition] of Object.entries(value as Record<string, unknown>)) {
    if (condition && typeof condition === 'object' && typeof (condition as { op?: unknown }).op === 'string') {
      result[field] = condition as Filters[string]
    }
  }
  return Object.keys(result).length > 0 ? result : undefined
}

export function validateTaskSearch(raw: Record<string, unknown>): TaskSearch {
  return {
    layout: pick(raw.layout, LAYOUTS),
    group: pick(raw.group, GROUPS),
    sort: pick(raw.sort, SORTS),
    dir: pick(raw.dir, ['asc', 'desc'] as const),
    filters: filtersOf(raw.filters),
  }
}

export const GROUP_OPTIONS = GROUPS
export const SORT_OPTIONS = SORTS
