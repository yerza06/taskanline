import { useInfiniteQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'

import { adminFetch } from '@/shared/api/admin'
import type { AdminUserPage, InstanceRole } from '@/shared/api/types'
import { formatDateTime } from '@/shared/lib/format'
import { ROLE_LABELS, STATUS_LABELS } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Input } from '@/shared/ui/Input'
import { PageTitle, TD, TH, Table } from '@/shared/ui/Page'
import { Select } from '@/shared/ui/Select'

export function UsersPage() {
  const [q, setQ] = useState('')
  const [role, setRole] = useState<InstanceRole | ''>('')
  const [status, setStatus] = useState('')
  const params = new URLSearchParams()
  if (q.trim()) params.set('q', q.trim())
  if (role) params.set('role', role)
  if (status) params.set('status', status)

  const users = useInfiniteQuery({
    queryKey: ['users', q.trim(), role, status],
    queryFn: ({ pageParam }) => {
      const page = new URLSearchParams(params)
      if (pageParam) page.set('cursor', pageParam)
      return adminFetch<AdminUserPage>(`/users?${page.toString()}`)
    },
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
  const rows = users.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <>
      <PageTitle title="Пользователи" />
      <div className="mb-4 flex flex-wrap gap-2" role="search">
        <Input
          aria-label="Поиск по email и имени"
          placeholder="Email или имя"
          className="h-9 w-64"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select aria-label="Роль" value={role} onChange={(e) => setRole(e.target.value as InstanceRole | '')}>
          <option value="">Любая роль</option>
          {(Object.keys(ROLE_LABELS) as InstanceRole[]).map((value) => (
            <option key={value} value={value}>
              {ROLE_LABELS[value]}
            </option>
          ))}
        </Select>
        <Select aria-label="Статус" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Любой статус</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      <Table label="Пользователи">
        <thead>
          <tr>
            <th className={TH}>Email</th>
            <th className={TH}>Имя</th>
            <th className={TH}>Роль</th>
            <th className={TH}>Статус</th>
            <th className={TH}>Последний раз</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((user) => (
            <tr key={user.id}>
              <td className={TD}>
                <Link to="/users/$userId" params={{ userId: user.id }} className="underline-offset-2 hover:underline">
                  {user.email}
                </Link>
              </td>
              <td className={TD}>{user.full_name}</td>
              <td className={TD}>{ROLE_LABELS[user.role]}</td>
              <td className={user.status === 'active' ? TD : `${TD} font-semibold`}>{STATUS_LABELS[user.status]}</td>
              <td className={`${TD} text-fg-muted`}>{user.last_seen_at ? formatDateTime(user.last_seen_at) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </Table>
      {rows.length === 0 && users.isSuccess && <p className="text-fg-muted mt-3 text-sm">Никого не найдено.</p>}
      {users.hasNextPage && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={() => void users.fetchNextPage()}>
          Показать ещё
        </Button>
      )}
    </>
  )
}
