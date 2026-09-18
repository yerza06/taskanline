import * as RadixDialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Модальное окно.
 *
 * Тонкая обёртка над Radix: фокус-ловушка, закрытие по Escape и связь
 * заголовка с окном через aria — всё это даётся примитивом и не должно
 * переписываться на каждом экране.
 */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <RadixDialog.Content className="border-border bg-surface text-fg fixed top-1/2 left-1/2 z-50 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border p-5 shadow-xl">
          <RadixDialog.Title className="font-display pr-6 text-lg font-semibold tracking-tight">
            {title}
          </RadixDialog.Title>
          <RadixDialog.Description className="text-fg-muted mt-1 text-sm">
            {description}
          </RadixDialog.Description>

          <div className="mt-4">{children}</div>

          <RadixDialog.Close
            aria-label="Закрыть"
            className="text-fg-muted hover:text-fg focus-visible:outline-accent absolute top-4 right-4 rounded transition focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            <X aria-hidden="true" className="size-4" />
          </RadixDialog.Close>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  )
}
