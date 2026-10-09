import { createFileRoute, useNavigate } from '@tanstack/react-router'

import { AuditPage, type AuditSearch } from '@/features/audit/AuditPage'
import type { AuditAction } from '@/shared/api/types'

function text(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined
}

export const Route = createFileRoute('/audit')({
  validateSearch: (raw: Record<string, unknown>): AuditSearch => ({
    action: text(raw.action) as AuditAction | undefined,
    target_id: text(raw.target_id),
    date_from: text(raw.date_from),
    date_to: text(raw.date_to),
  }),
  component: Page,
})

function Page() {
  const search = Route.useSearch()
  const navigate = useNavigate()
  return (
    <AuditPage
      search={search}
      onSearch={(next) =>
        void navigate({
          to: '/audit',
          search: Object.fromEntries(Object.entries(next).filter(([, v]) => v !== undefined)),
          replace: true,
        })
      }
    />
  )
}
