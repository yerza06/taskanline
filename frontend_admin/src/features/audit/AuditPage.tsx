import { useInfiniteQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'

import { adminFetch } from '@/shared/api/admin'
import type { AuditAction, AuditPage as Page } from '@/shared/api/types'
import { formatDateTime } from '@/shared/lib/format'
import { ACTION_LABELS } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Input } from '@/shared/ui/Input'
import { PageTitle } from '@/shared/ui/Page'
import { Select } from '@/shared/ui/Select'

export interface AuditSearch {
  action?: AuditAction
  target_id?: string
  date_from?: string
  date_to?: string
}

/**
 * Журнал аудита. Главный вопрос — «что произошло с этим пользователем и кто это
 * сделал», поэтому фильтр по цели ставится из карточки пользователя одной ссылкой.
 * Фильтры живут в адресе: ссылку на выборку можно переслать.
 */
export function AuditPage({ search, onSearch }: { search: AuditSearch; onSearch: (s: AuditSearch) => void }) {
  const entries = useInfiniteQuery({
    queryKey: ['audit', search],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams()
      for (const [key, value] of Object.entries(search)) if (value) params.set(key, String(value))
      if (pageParam) params.set('cursor', pageParam)
      return adminFetch<Page>(`/audit?${params.toString()}`)
    },
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
  const rows = entries.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <>
      <PageTitle title="Журнал аудита" hint="Записи не редактируются и не удаляются — никем." />
      <div className="mb-4 flex flex-wrap items-end gap-2" role="search">
        <Select
          aria-label="Действие"
          value={search.action ?? ''}
          onChange={(e) => onSearch({ ...search, action: (e.target.value || undefined) as AuditAction | undefined })}
        >
          <option value="">Все действия</option>
          {(Object.keys(ACTION_LABELS) as AuditAction[]).map((value) => (
            <option key={value} value={value}>
              {ACTION_LABELS[value]}
            </option>
          ))}
        </Select>
        <label className="text-fg-muted flex items-center gap-1 text-sm">
          с
          <Input
            aria-label="С даты"
            type="date"
            className="h-9 w-40"
            value={search.date_from ?? ''}
            onChange={(e) => onSearch({ ...search, date_from: e.target.value || undefined })}
          />
        </label>
        <label className="text-fg-muted flex items-center gap-1 text-sm">
          по
          <Input
            aria-label="По дату"
            type="date"
            className="h-9 w-40"
            value={search.date_to ?? ''}
            onChange={(e) => onSearch({ ...search, date_to: e.target.value || undefined })}
          />
        </label>
        {search.target_id && (
          <Button variant="ghost" size="sm" onClick={() => onSearch({ ...search, target_id: undefined })}>
            Снять фильтр по цели
          </Button>
        )}
      </div>
      <ul className="divide-border border-border bg-surface divide-y rounded-lg border">
        {rows.map((entry) => (
          <li key={entry.id} className="px-3 py-2 text-sm">
            <details>
              <summary className="flex cursor-pointer flex-wrap gap-x-3">
                <span className="font-medium">{ACTION_LABELS[entry.action]}</span>
                <span className="text-fg-muted">{entry.actor.email}</span>
                <span className="text-fg-muted">{entry.ip ?? '—'}</span>
                <span className="text-fg-muted ml-auto">{formatDateTime(entry.created_at)}</span>
              </summary>
              <div className="mt-2 space-y-1">
                {entry.target_type === 'user' && entry.target_id && (
                  <Link to="/users/$userId" params={{ userId: entry.target_id }} className="underline underline-offset-4">
                    Карточка пользователя
                  </Link>
                )}
                {entry.target_type === 'workspace' && entry.target_id && entry.action !== 'workspace_deleted' && (
                  <Link
                    to="/workspaces/$workspaceId"
                    params={{ workspaceId: entry.target_id }}
                    className="underline underline-offset-4"
                  >
                    Карточка пространства
                  </Link>
                )}
                <pre className="bg-surface-hover overflow-x-auto rounded p-2 text-xs">
                  {JSON.stringify(entry.payload, null, 2)}
                </pre>
                {entry.user_agent && <p className="text-fg-muted text-xs">{entry.user_agent}</p>}
              </div>
            </details>
          </li>
        ))}
        {rows.length === 0 && entries.isSuccess && <li className="text-fg-muted px-3 py-2 text-sm">Записей нет.</li>}
      </ul>
      {entries.hasNextPage && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={() => void entries.fetchNextPage()}>
          Показать ещё
        </Button>
      )}
    </>
  )
}
