import type { ReactNode } from 'react'

import { ThemeToggle } from '@/shared/theme/ThemeToggle'

/** Общая рамка экранов входа и регистрации. */
export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string
  description: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <div className="bg-canvas text-fg flex min-h-full flex-col">
      <div className="flex justify-end p-4">
        <ThemeToggle />
      </div>

      <div className="flex flex-1 items-start justify-center px-4 pb-10 sm:items-center sm:pb-16">
        <div className="border-border bg-surface w-full max-w-sm rounded-lg border p-6 shadow-sm">
          <h1 className="text-xl font-medium">{title}</h1>
          <p className="text-fg-muted mt-1 text-sm">{description}</p>

          <div className="mt-6">{children}</div>

          <div className="text-fg-muted mt-6 text-sm">{footer}</div>
        </div>
      </div>
    </div>
  )
}
