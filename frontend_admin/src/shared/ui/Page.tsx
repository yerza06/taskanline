import type { ReactNode } from 'react'

export function PageTitle({ title, hint, actions }: { title: string; hint?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end gap-3">
      <div className="min-w-0 flex-1">
        <h1 className="font-display text-2xl font-semibold tracking-tight">{title}</h1>
        {hint && <p className="text-fg-muted mt-1 text-sm">{hint}</p>}
      </div>
      {actions}
    </div>
  )
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="border-border bg-surface space-y-3 rounded-lg border p-4">
      <h2 className="text-fg-muted text-xs tracking-wide uppercase">{title}</h2>
      {children}
    </section>
  )
}

/** Таблица с прокруткой вбок на узком экране — страница от неё не растягивается. */
export function Table({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="overflow-x-auto">
      <table aria-label={label} className="w-full min-w-[36rem] border-collapse text-left text-sm">
        {children}
      </table>
    </div>
  )
}

export const TH = 'border-border text-fg-muted border-b px-2 py-1.5 text-xs font-normal'
export const TD = 'border-border border-b px-2 py-1.5 align-top'
