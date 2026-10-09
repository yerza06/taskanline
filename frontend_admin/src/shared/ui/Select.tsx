import type { SelectHTMLAttributes } from 'react'

import { cn } from '@/shared/lib/cn'

/**
 * Нативный выпадающий список.
 *
 * Нативный, а не нарисованный: клавиатура, скринридер и экран телефона работают
 * с ним из коробки, а для выбора статуса или приоритета большего не нужно.
 */
export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        'border-border bg-surface text-fg h-9 rounded-md border px-2 text-sm',
        'focus-visible:outline-accent focus-visible:outline-2 focus-visible:outline-offset-0',
        'disabled:opacity-60',
        className,
      )}
      {...props}
    />
  )
}
