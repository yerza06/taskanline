import type { ReactNode } from 'react'

import { cn } from '@/shared/lib/cn'

/**
 * Сообщение об ошибке запроса.
 *
 * `role="alert"` — чтобы отказ сервера дошёл и до того, кто не смотрит на
 * экран: без него сообщение появляется молча.
 */
export function Alert({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      role="alert"
      className={cn(
        'border-danger bg-danger-surface text-danger rounded-md border px-3 py-2 text-sm',
        className,
      )}
    >
      {children}
    </div>
  )
}
