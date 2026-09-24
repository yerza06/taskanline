import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Link } from '@tanstack/react-router'
import { ChevronDown, KeyRound, LogOut, User } from 'lucide-react'
import type { ReactNode } from 'react'

import { canWrite, useLogout, useSession } from '@/features/auth/api/session'
import { ROLE_LABELS } from '@/features/auth/model/roles'
import { ThemeToggle } from '@/shared/theme/ThemeToggle'

const ITEM_CLASS =
  'flex w-full cursor-default items-center gap-2 rounded px-2 py-1.5 text-sm outline-none data-highlighted:bg-surface-hover'

/**
 * Оболочка защищённой части приложения.
 *
 * Боковой навигации нет намеренно: до этапа 3 из неё некуда вести, а пустое
 * меню из трёх неработающих пунктов хуже его отсутствия.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const session = useSession()
  const logout = useLogout()

  return (
    <div className="bg-canvas text-fg flex h-full flex-col">
      <header
        role="banner"
        className="border-border bg-surface flex h-14 shrink-0 items-center gap-3 border-b px-4"
      >
        <Link to="/profile" className="font-display text-lg font-semibold tracking-tight">
          TasKanLine
        </Link>

        {session && !canWrite(session) && (
          <span className="border-border text-fg-muted rounded-full border px-2 py-0.5 text-xs">
            Только чтение
          </span>
        )}

        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />

          {/* Меню немодальное: страница под ним остаётся прокручиваемой и видимой
              скринридеру. Модальность здесь ничего не защищает — это три пункта,
              а не диалог подтверждения. */}
          {session && (
            <DropdownMenu.Root modal={false}>
              <DropdownMenu.Trigger className="hover:bg-surface-hover focus-visible:outline-accent flex items-center gap-2 rounded-md px-2 py-1.5 text-left transition focus-visible:outline-2 focus-visible:outline-offset-2">
                <span className="min-w-0">
                  <span className="block truncate text-sm">{session.full_name}</span>
                  <span className="text-fg-muted block truncate text-xs">
                    {ROLE_LABELS[session.role]}
                  </span>
                </span>
                <ChevronDown aria-hidden="true" className="size-4 shrink-0" />
              </DropdownMenu.Trigger>

              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  align="end"
                  sideOffset={6}
                  className="border-border bg-surface z-50 min-w-48 rounded-md border p-1 shadow-lg"
                >
                  <DropdownMenu.Item asChild className={ITEM_CLASS}>
                    <Link to="/profile">
                      <User aria-hidden="true" className="size-4" />
                      Профиль
                    </Link>
                  </DropdownMenu.Item>
                  <DropdownMenu.Item asChild className={ITEM_CLASS}>
                    <Link to="/tokens">
                      <KeyRound aria-hidden="true" className="size-4" />
                      Токены доступа
                    </Link>
                  </DropdownMenu.Item>
                  <DropdownMenu.Separator className="bg-border my-1 h-px" />
                  <DropdownMenu.Item className={ITEM_CLASS} onSelect={() => logout.mutate()}>
                    <LogOut aria-hidden="true" className="size-4" />
                    Выйти
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          )}
        </div>
      </header>

      <main className="min-w-0 flex-1 overflow-auto">{children}</main>
    </div>
  )
}
