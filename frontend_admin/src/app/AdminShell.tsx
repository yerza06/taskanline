import { Link } from '@tanstack/react-router'
import { Gauge, History, Settings, Users, Building2 } from 'lucide-react'
import type { ReactNode } from 'react'

import { ReauthDialog } from '@/app/ReauthDialog'
import { useAdminSession } from '@/app/session'
import { ROLE_LABELS } from '@/shared/lib/labels'
import { ThemeToggle } from '@/shared/theme/ThemeToggle'

const LINK =
  'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm text-fg-muted hover:bg-surface-hover hover:text-fg'
const ACTIVE = { className: 'bg-surface-hover font-semibold text-fg' }

const NAV = [
  { to: '/', label: 'Обзор', icon: Gauge, exact: true },
  { to: '/users', label: 'Пользователи', icon: Users, exact: false },
  { to: '/workspaces', label: 'Пространства', icon: Building2, exact: false },
  { to: '/audit', label: 'Журнал', icon: History, exact: false },
  { to: '/settings', label: 'Настройки', icon: Settings, exact: false },
] as const

/**
 * Оболочка админ-панели. Задач, проектов и комментариев здесь нет и не будет:
 * панель управляет сервером и людьми, а не их работой (админ-спека §1).
 */
export function AdminShell({ children }: { children: ReactNode }) {
  const session = useAdminSession()
  return (
    <div className="bg-canvas text-fg flex min-h-full flex-col">
      <header className="border-border bg-surface flex flex-wrap items-center gap-3 border-b px-4 py-2">
        <span className="font-display text-lg font-semibold tracking-tight">TasKanLine</span>
        <span className="border-border rounded-full border px-2 py-0.5 text-xs font-semibold">
          Администрирование
        </span>
        <nav aria-label="Разделы" className="order-last flex w-full flex-wrap gap-1 md:order-none md:ml-4 md:w-auto">
          {NAV.map(({ to, label, icon: Icon, exact }) => (
            <Link key={to} to={to} activeOptions={{ exact }} activeProps={ACTIVE} className={LINK}>
              <Icon aria-hidden="true" className="size-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {session && (
            <span className="text-right text-xs">
              <span className="block">{session.email}</span>
              <span className="text-fg-muted block">{ROLE_LABELS[session.role]}</span>
            </span>
          )}
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 p-4 sm:p-6">{children}</main>
      <ReauthDialog />
    </div>
  )
}
