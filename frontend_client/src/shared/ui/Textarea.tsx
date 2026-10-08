import type { TextareaHTMLAttributes } from 'react'

import { cn } from '@/shared/lib/cn'

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        'border-border bg-surface text-fg placeholder:text-fg-muted w-full rounded-md border px-3 py-2 text-sm',
        'focus-visible:outline-accent focus-visible:outline-2 focus-visible:outline-offset-0',
        'aria-invalid:border-danger disabled:opacity-60',
        className,
      )}
      {...props}
    />
  )
}
