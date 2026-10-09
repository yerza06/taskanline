import type { InputHTMLAttributes } from 'react'

import { cn } from '@/shared/lib/cn'

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'border-border bg-surface text-fg placeholder:text-fg-muted h-10 w-full rounded-md border px-3 text-sm',
        // Без отступа: кольцо ложится на границу поля, а не рисует вторую рамку рядом.
        'focus-visible:outline-accent focus-visible:outline-2 focus-visible:outline-offset-0',
        'aria-invalid:border-danger disabled:opacity-60',
        className,
      )}
      {...props}
    />
  )
}
