import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { ChevronDown, Plus, X } from 'lucide-react'

import { PRIORITY_LABELS, STATE_TYPE_LABELS, STATE_TYPES } from '@/features/tasks/model/labels'
import type { Directory } from '@/features/tasks/model/groups'
import { FIELDS } from '@/features/views/model/filters'
import type { FilterCondition, Filters } from '@/shared/api/types'
import { Input } from '@/shared/ui/Input'
import { Select } from '@/shared/ui/Select'

/**
 * Конструктор фильтров: строки «поле · условие · значение», соединённые через И.
 *
 * Собирает ровно грамматику views (§4 модели данных) — тот же объект уходит и в
 * `POST /views/query`, и в сохранённый view, и тот же понимает CLI. Своего
 * языка фильтров у интерфейса нет.
 */

const OP_LABELS: Record<string, string> = {
  in: 'любой из',
  nin: 'ни один из',
  is_null: 'не задан',
  not_null: 'задан',
  lt: 'раньше',
  lte: 'не позже',
  eq: 'равно',
  gte: 'не раньше',
  gt: 'позже',
  contains: 'содержит',
}

const PRIORITY_OP_LABELS: Record<string, string> = {
  in: 'любой из',
  lte: 'не ниже',
  gte: 'не выше',
}

const ME = '@me'

function options(field: string, dir: Directory): { value: string; label: string }[] {
  switch (field) {
    case 'team_id':
      return dir.teams.map((team) => ({ value: team.id, label: `${team.key} · ${team.name}` }))
    case 'project_id':
      return dir.projects.map((project) => ({ value: project.id, label: project.name }))
    case 'state_id':
      return dir.states.map((state) => {
        const team = dir.teams.find((t) => t.id === state.team_id)
        return { value: state.id, label: team ? `${state.name} · ${team.key}` : state.name }
      })
    case 'assignee_id':
    case 'creator_id':
      return [
        { value: ME, label: 'Я' },
        ...dir.members.map((member) => ({ value: member.user_id, label: member.full_name })),
      ]
    case 'label_id':
      return dir.labels.map((label) => ({ value: label.id, label: label.name }))
    case 'state_type':
      return STATE_TYPES.map((type) => ({ value: type, label: STATE_TYPE_LABELS[type] }))
    case 'priority':
      return [1, 2, 3, 4, 0].map((p) => ({ value: String(p), label: PRIORITY_LABELS[p] ?? '' }))
  }
  return []
}

function defaultCondition(field: string): FilterCondition {
  const spec = FIELDS[field]
  switch (spec?.kind) {
    case 'bool':
      return { op: 'eq', value: true }
    case 'text':
      return { op: 'contains', value: '' }
    case 'date':
      return { op: 'lte', value: '@today' }
    case 'priority':
      return { op: 'in', value: [] }
    default:
      return { op: 'in', value: field === 'assignee_id' ? [ME] : [] }
  }
}

function MultiValue({
  field,
  condition,
  dir,
  onChange,
}: {
  field: string
  condition: FilterCondition
  dir: Directory
  onChange: (condition: FilterCondition) => void
}) {
  const all = options(field, dir)
  const chosen = new Set((Array.isArray(condition.value) ? condition.value : []).map(String))
  const asNumbers = field === 'priority'
  const summary = all.filter((option) => chosen.has(option.value)).map((option) => option.label)

  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger className="border-border bg-surface hover:bg-surface-hover focus-visible:outline-accent flex h-9 max-w-64 min-w-32 items-center gap-1 rounded-md border px-2 text-left text-sm focus-visible:outline-2">
        <span className="min-w-0 flex-1 truncate">{summary.length ? summary.join(', ') : 'Выберите…'}</span>
        <ChevronDown aria-hidden="true" className="size-4 shrink-0" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={4}
          className="border-border bg-surface z-50 max-h-72 min-w-48 overflow-y-auto rounded-md border p-1 shadow-lg"
        >
          {all.map((option) => (
            <DropdownMenu.CheckboxItem
              key={option.value}
              checked={chosen.has(option.value)}
              // Список остаётся открытым: выбирают обычно несколько значений подряд.
              onSelect={(event) => event.preventDefault()}
              onCheckedChange={(checked) => {
                const next = new Set(chosen)
                if (checked) next.add(option.value)
                else next.delete(option.value)
                const values = [...next]
                onChange({ ...condition, value: asNumbers ? values.map(Number) : values })
              }}
              className="data-highlighted:bg-surface-hover flex cursor-default items-center gap-2 rounded px-2 py-1.5 text-sm outline-none"
            >
              <span className="border-border grid size-4 place-items-center rounded-sm border">
                <DropdownMenu.ItemIndicator>✓</DropdownMenu.ItemIndicator>
              </span>
              {option.label}
            </DropdownMenu.CheckboxItem>
          ))}
          {all.length === 0 && <p className="text-fg-muted px-2 py-1.5 text-sm">Нечего выбрать</p>}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

function ValueInput({
  field,
  condition,
  dir,
  onChange,
}: {
  field: string
  condition: FilterCondition
  dir: Directory
  onChange: (condition: FilterCondition) => void
}) {
  const spec = FIELDS[field]
  if (!spec || condition.op === 'is_null' || condition.op === 'not_null') return null
  const label = `Значение: ${spec.label}`

  if (spec.kind === 'bool') {
    return (
      <Select
        aria-label={label}
        value={condition.value ? 'true' : 'false'}
        onChange={(event) => onChange({ ...condition, value: event.target.value === 'true' })}
      >
        <option value="true">да</option>
        <option value="false">нет</option>
      </Select>
    )
  }
  if (spec.kind === 'priority' && condition.op !== 'in') {
    return (
      <Select
        aria-label={label}
        value={typeof condition.value === 'number' ? condition.value : 2}
        onChange={(event) => onChange({ ...condition, value: Number(event.target.value) })}
      >
        {[1, 2, 3, 4].map((p) => (
          <option key={p} value={p}>
            {PRIORITY_LABELS[p]}
          </option>
        ))}
      </Select>
    )
  }
  if (spec.kind === 'date' || spec.kind === 'text') {
    return (
      <Input
        aria-label={label}
        className="h-9 w-44"
        value={typeof condition.value === 'string' ? condition.value : ''}
        placeholder={spec.kind === 'date' ? '2026-10-31 или @today+7d' : 'часть названия'}
        onChange={(event) => onChange({ ...condition, value: event.target.value })}
      />
    )
  }
  return <MultiValue field={field} condition={condition} dir={dir} onChange={onChange} />
}

export function FilterBuilder({
  filters,
  dir,
  onChange,
  hidden = [],
}: {
  filters: Filters
  dir: Directory
  onChange: (filters: Filters) => void
  /** Поля, заданные самим экраном (команда на странице команды), — не показываются. */
  hidden?: string[]
}) {
  const used = Object.keys(filters)
  const available = Object.keys(FIELDS).filter((field) => !used.includes(field) && !hidden.includes(field))

  return (
    <div className="space-y-2" role="group" aria-label="Фильтры">
      {used.map((field) => {
        const spec = FIELDS[field]
        const condition = filters[field]
        if (!spec || !condition) return null
        const update = (next: FilterCondition) => onChange({ ...filters, [field]: next })
        const opLabels = spec.kind === 'priority' ? PRIORITY_OP_LABELS : OP_LABELS
        return (
          <div key={field} className="flex flex-wrap items-center gap-2">
            <span className="w-28 text-sm font-medium">{spec.label}</span>
            <Select
              aria-label={`Условие: ${spec.label}`}
              value={condition.op}
              onChange={(event) => {
                const op = event.target.value
                const value =
                  op === 'is_null' || op === 'not_null'
                    ? undefined
                    : spec.kind === 'priority'
                      ? op === 'in' ? [] : 2
                      : condition.value
                update(value === undefined ? { op } : { op, value })
              }}
            >
              {spec.ops.map((op) => (
                <option key={op} value={op}>
                  {opLabels[op]}
                </option>
              ))}
            </Select>
            <ValueInput field={field} condition={condition} dir={dir} onChange={update} />
            <button
              type="button"
              aria-label={`Убрать условие: ${spec.label}`}
              onClick={() => {
                const next = { ...filters }
                delete next[field]
                onChange(next)
              }}
              className="text-fg-muted hover:text-fg hover:bg-surface-hover focus-visible:outline-accent rounded p-1 focus-visible:outline-2"
            >
              <X aria-hidden="true" className="size-4" />
            </button>
          </div>
        )
      })}

      {available.length > 0 && (
        <DropdownMenu.Root modal={false}>
          <DropdownMenu.Trigger className="text-fg-muted hover:text-fg hover:bg-surface-hover focus-visible:outline-accent flex items-center gap-1 rounded px-2 py-1 text-sm focus-visible:outline-2">
            <Plus aria-hidden="true" className="size-4" />
            Условие
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="start"
              sideOffset={4}
              className="border-border bg-surface z-50 min-w-48 rounded-md border p-1 shadow-lg"
            >
              {available.map((field) => (
                <DropdownMenu.Item
                  key={field}
                  onSelect={() => onChange({ ...filters, [field]: defaultCondition(field) })}
                  className="data-highlighted:bg-surface-hover cursor-default rounded px-2 py-1.5 text-sm outline-none"
                >
                  {FIELDS[field]?.label}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      )}
    </div>
  )
}
