import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'

import { adminFetch } from '@/shared/api/admin'
import type { AuditPage, Stats } from '@/shared/api/types'
import { formatDateTime } from '@/shared/lib/format'
import { ACTION_LABELS } from '@/shared/lib/labels'
import { PageTitle, Section } from '@/shared/ui/Page'

function Tile({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="border-border bg-surface rounded-lg border p-4">
      <p className="text-fg-muted text-xs tracking-wide uppercase">{label}</p>
      <p className="font-display mt-1 text-3xl font-semibold">{value}</p>
      {hint && <p className="text-fg-muted mt-1 text-xs">{hint}</p>}
    </div>
  )
}

/** Дашборд: за один взгляд — всё ли в порядке. Не система мониторинга. */
export function DashboardPage() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: () => adminFetch<Stats>('/stats') }).data
  const recent = useQuery({
    queryKey: ['audit', 'recent'],
    queryFn: () => adminFetch<AuditPage>('/audit?limit=5'),
  }).data
  const behind = stats && stats.migration !== stats.migration_head

  return (
    <>
      <PageTitle title="Обзор" hint="Сервер и люди на нём — без содержимого рабочих пространств." />
      {stats && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile
            label="Пользователи"
            value={stats.users.total}
            hint={`активных ${stats.users.active} · заблокировано ${stats.users.blocked} · удалено ${stats.users.deleted}`}
          />
          <Tile label="Пространства" value={stats.workspaces} />
          <Tile label="Команды" value={stats.teams} />
          <Tile label="Задачи" value={stats.tasks} />
        </div>
      )}
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Section title="Версия">
          {stats && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-fg-muted">Приложение</dt>
              <dd>{stats.version}</dd>
              <dt className="text-fg-muted">Миграции</dt>
              <dd className={behind ? 'font-semibold' : ''}>
                {stats.migration ?? '—'}
                {behind ? ` — в коде есть ${stats.migration_head ?? '?'}, примените миграции` : ' — актуальны'}
              </dd>
            </dl>
          )}
        </Section>
        <Section title="Последние действия">
          <ul className="space-y-1 text-sm">
            {(recent?.items ?? []).map((entry) => (
              <li key={entry.id} className="flex flex-wrap gap-x-2">
                <span>{ACTION_LABELS[entry.action]}</span>
                <span className="text-fg-muted">
                  {entry.actor.email} · {formatDateTime(entry.created_at)}
                </span>
              </li>
            ))}
            {recent?.items.length === 0 && <li className="text-fg-muted">Журнал пуст.</li>}
          </ul>
          <Link to="/audit" className="text-sm underline underline-offset-4">
            Весь журнал
          </Link>
        </Section>
      </div>
    </>
  )
}
