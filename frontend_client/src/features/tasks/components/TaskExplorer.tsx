import { useNavigate } from '@tanstack/react-router'
import { Columns3, Filter, List, Save } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'

import { canWrite, useSession } from '@/features/auth/api/session'
import { TaskBoard } from '@/features/tasks/components/TaskBoard'
import { TaskList } from '@/features/tasks/components/TaskList'
import { taskQueryOptions, useMoveTask, useTaskQuery, type TaskQueryParams } from '@/features/tasks/api/tasks'
import { boardColumns, groupTitle, useDirectory } from '@/features/tasks/model/groups'
import { GROUP_LABELS, SORT_LABELS } from '@/features/tasks/model/labels'
import { GROUP_OPTIONS, SORT_OPTIONS, type TaskSearch } from '@/features/tasks/model/search'
import { useStates } from '@/features/teams/api/teams'
import { FilterBuilder } from '@/features/views/components/FilterBuilder'
import { completeFilters } from '@/features/views/model/filters'
import { SaveViewDialog, type ViewDraft } from '@/features/views/components/SaveViewDialog'
import { humanMessage } from '@/shared/api/messages'
import type { Filters, TeamRead, ViewGroupBy, WorkspaceRead } from '@/shared/api/types'
import { cn } from '@/shared/lib/cn'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Select } from '@/shared/ui/Select'

export interface ExplorerDefaults {
  layout: 'list' | 'board'
  group: ViewGroupBy | 'none'
  sort: TaskSearch['sort'] & string
  dir: 'asc' | 'desc'
  filters: Filters
}

/**
 * Срез задач: панель (вид, группировка, сортировка, фильтры) и список или доска.
 *
 * Один компонент на «мои задачи», команду, проект и view: различаются только
 * базовые условия экрана (`scope` — например, `team_id` команды), которые
 * пользователь не снимает, и значения по умолчанию.
 */
export function TaskExplorer({
  workspace,
  title,
  subtitle,
  scope,
  team,
  search,
  defaults,
  onSearch,
  actions,
  allowSave = true,
}: {
  workspace: WorkspaceRead
  title: string
  subtitle?: ReactNode
  scope: Filters
  team?: TeamRead
  search: TaskSearch
  defaults: ExplorerDefaults
  onSearch: (search: TaskSearch) => void
  actions?: ReactNode
  allowSave?: boolean
}) {
  const writable = canWrite(useSession())
  const dir = useDirectory(workspace.id)
  const teamStates = useStates(team?.id).data
  const navigate = useNavigate()
  const [filtersOpen, setFiltersOpen] = useState(Boolean(search.filters))
  const [saving, setSaving] = useState(false)

  const layout = search.layout ?? defaults.layout
  // Колонки доски — группы; без группировки доска раскладывается по статусам.
  const chosenGroup = search.group ?? defaults.group
  const group = layout === 'board' && chosenGroup === 'none' ? 'state' : chosenGroup
  const sort = search.sort ?? defaults.sort
  const direction = search.dir ?? defaults.dir
  const filters = search.filters ?? defaults.filters
  const effective = completeFilters({ ...filters, ...scope })

  const params: TaskQueryParams = {
    workspaceId: workspace.id,
    filters: effective,
    sortBy: sort,
    sortDirection: direction,
    groupBy: group === 'none' ? null : group,
  }
  const query = useTaskQuery(params)
  const move = useMoveTask(taskQueryOptions(params).queryKey)
  const groups = query.data?.groups ?? []
  const groupBy = params.groupBy
  const rules = {
    reorder: sort === 'manual' && writable,
    acrossGroups: groupBy === 'state' && writable,
  }
  const titleOf = (g: { key: string | null }) => groupTitle(groupBy, g.key, dir)
  const set = (patch: TaskSearch) => onSearch({ ...search, ...patch })

  const draft: ViewDraft = {
    filters: completeFilters({ ...filters, ...scope }),
    group_by: group === 'none' ? null : group,
    sort_by: sort,
    sort_direction: direction,
    layout,
  }
  const total = groups.reduce((sum, g) => sum + g.count, 0)

  // Клавиша `/`: открыть фильтры, добавить условие по названию и встать в него.
  useEffect(() => {
    function onSearchKey() {
      setFiltersOpen(true)
      if (!filters.title) {
        onSearch({ ...search, filters: { ...filters, title: { op: 'contains', value: '' } } })
      }
      window.setTimeout(() => {
        document.querySelector<HTMLInputElement>('input[aria-label="Значение: Название"]')?.focus()
      }, 0)
    }
    window.addEventListener('tkl:search', onSearchKey)
    return () => window.removeEventListener('tkl:search', onSearchKey)
  }, [filters, onSearch, search])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="border-border space-y-3 border-b px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="font-display truncate text-xl font-semibold tracking-tight">{title}</h1>
            {subtitle && <p className="text-fg-muted text-sm">{subtitle}</p>}
          </div>
          {actions}
        </div>

        <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Вид списка">
          <div className="border-border flex rounded-md border p-0.5" role="radiogroup" aria-label="Вид">
            {(['list', 'board'] as const).map((value) => {
              const Icon = value === 'list' ? List : Columns3
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={layout === value}
                  onClick={() => set({ layout: value })}
                  className={cn(
                    'flex items-center gap-1 rounded px-2 py-1 text-sm',
                    layout === value ? 'bg-accent text-accent-fg' : 'hover:bg-surface-hover',
                  )}
                >
                  <Icon aria-hidden="true" className="size-4" />
                  {value === 'list' ? 'Список' : 'Доска'}
                </button>
              )
            })}
          </div>

          <Select
            aria-label="Группировка"
            value={group}
            onChange={(e) => set({ group: e.target.value as TaskSearch['group'] })}
          >
            {GROUP_OPTIONS.filter((value) => layout === 'list' || value !== 'none').map((value) => (
              <option key={value} value={value}>
                {GROUP_LABELS[value]}
              </option>
            ))}
          </Select>

          <Select
            aria-label="Сортировка"
            value={sort}
            onChange={(e) => set({ sort: e.target.value as TaskSearch['sort'] })}
          >
            {SORT_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {SORT_LABELS[value]}
              </option>
            ))}
          </Select>
          {sort !== 'manual' && (
            <Select
              aria-label="Направление"
              value={direction}
              onChange={(e) => set({ dir: e.target.value as 'asc' | 'desc' })}
            >
              <option value="asc">По возрастанию</option>
              <option value="desc">По убыванию</option>
            </Select>
          )}

          <Button
            variant="secondary"
            size="sm"
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen((open) => !open)}
          >
            <Filter aria-hidden="true" className="size-4" />
            Фильтры
            {Object.keys(filters).length > 0 && (
              <span className="font-semibold">{Object.keys(filters).length}</span>
            )}
          </Button>

          {allowSave && writable && (
            <Button variant="ghost" size="sm" onClick={() => setSaving(true)}>
              <Save aria-hidden="true" className="size-4" />
              Сохранить как view
            </Button>
          )}

          <span className="text-fg-muted ml-auto text-sm" aria-live="polite">
            {query.isSuccess ? `Задач: ${total}` : ''}
          </span>
        </div>

        {filtersOpen && (
          <FilterBuilder
            filters={filters}
            dir={dir}
            hidden={Object.keys(scope)}
            onChange={(next) => set({ filters: Object.keys(next).length ? next : undefined })}
          />
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        {query.error && <Alert className="m-4">{humanMessage(query.error)}</Alert>}
        {move.error && <Alert className="m-4">{humanMessage(move.error)}</Alert>}
        {query.isSuccess && total === 0 && layout === 'list' ? (
          <p className="text-fg-muted p-8 text-center text-sm">
            Задач нет. Создать новую — клавиша <kbd className="border-border rounded border px-1">c</kbd>.
          </p>
        ) : layout === 'board' ? (
          <TaskBoard
            workspace={workspace.slug}
            columns={groupBy === 'state' ? boardColumns(groups, teamStates) : groups}
            title={titleOf}
            rules={rules}
            onMove={(request) => move.mutate(request)}
          />
        ) : (
          <TaskList
            workspace={workspace.slug}
            groups={groups}
            title={titleOf}
            rules={rules}
            onMove={(request) => move.mutate(request)}
          />
        )}
      </div>

      {saving && (
        <SaveViewDialog
          workspaceId={workspace.id}
          teams={dir.teams}
          defaultTeamId={team?.id}
          draft={draft}
          open
          onOpenChange={setSaving}
          onSaved={(view) => {
            setSaving(false)
            void navigate({
              to: '/w/$workspace/view/$viewId',
              params: { workspace: workspace.slug, viewId: view.id },
            })
          }}
        />
      )}
    </div>
  )
}
