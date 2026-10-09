import { useInfiniteQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'

import { adminFetch } from '@/shared/api/admin'
import type { AdminWorkspacePage } from '@/shared/api/types'
import { formatDateTime } from '@/shared/lib/format'
import { Button } from '@/shared/ui/Button'
import { Input } from '@/shared/ui/Input'
import { PageTitle, TD, TH, Table } from '@/shared/ui/Page'
import { Select } from '@/shared/ui/Select'

const SORTS: Record<string, string> = {
  created: 'Новые первыми',
  name: 'По названию',
  members: 'По числу участников',
  tasks: 'По числу задач',
  activity: 'Давно без активности',
}

/** Список пространств: сортировка по размеру и давности активности находит брошенные. */
export function WorkspacesPage() {
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('created')
  const spaces = useInfiniteQuery({
    queryKey: ['workspaces', q.trim(), sort],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ sort })
      if (q.trim()) params.set('q', q.trim())
      if (pageParam) params.set('cursor', pageParam)
      return adminFetch<AdminWorkspacePage>(`/workspaces?${params.toString()}`)
    },
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
  const rows = spaces.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <>
      <PageTitle title="Рабочие пространства" hint="Названия и счётчики — без содержимого." />
      <div className="mb-4 flex flex-wrap gap-2" role="search">
        <Input
          aria-label="Поиск по названию и адресу"
          placeholder="Название или адрес"
          className="h-9 w-64"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select aria-label="Сортировка" value={sort} onChange={(e) => setSort(e.target.value)}>
          {Object.entries(SORTS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      <Table label="Рабочие пространства">
        <thead>
          <tr>
            <th className={TH}>Название</th>
            <th className={TH}>Владельцы</th>
            <th className={TH}>Участники</th>
            <th className={TH}>Команды</th>
            <th className={TH}>Задачи</th>
            <th className={TH}>Последняя активность</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td className={TD}>
                <Link
                  to="/workspaces/$workspaceId"
                  params={{ workspaceId: row.id }}
                  className="underline-offset-2 hover:underline"
                >
                  {row.name}
                </Link>
                <span className="text-fg-muted block text-xs">/{row.slug}</span>
              </td>
              <td className={TD}>{row.owners.map((o) => o.email).join(', ') || '—'}</td>
              <td className={TD}>{row.members}</td>
              <td className={TD}>{row.teams}</td>
              <td className={TD}>{row.tasks}</td>
              <td className={`${TD} text-fg-muted`}>
                {row.last_activity_at ? formatDateTime(row.last_activity_at) : 'не было'}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      {rows.length === 0 && spaces.isSuccess && <p className="text-fg-muted mt-3 text-sm">Пространств нет.</p>}
      {spaces.hasNextPage && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={() => void spaces.fetchNextPage()}>
          Показать ещё
        </Button>
      )}
    </>
  )
}
