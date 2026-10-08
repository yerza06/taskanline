import {
  Circle,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleX,
  Minus,
  OctagonAlert,
  SignalHigh,
  SignalLow,
  SignalMedium,
} from 'lucide-react'

import { PRIORITY_LABELS, STATE_TYPE_LABELS } from '@/features/tasks/model/labels'
import type { StateType } from '@/shared/api/types'
import { cn } from '@/shared/lib/cn'

/**
 * Статус и приоритет показываются формой значка, а не цветом: палитра
 * чёрно-белая (архитектура §4.4). Пустой пунктир — бэклог, точка — в работе,
 * галочка — сделано; срочный приоритет — восьмиугольник, остальные — «сигнал».
 */
const STATE_ICONS = {
  backlog: CircleDashed,
  unstarted: Circle,
  started: CircleDot,
  completed: CircleCheck,
  canceled: CircleX,
} as const

export function StateIcon({ type, className }: { type: StateType; className?: string }) {
  const Icon = STATE_ICONS[type]
  return (
    <Icon
      role="img"
      aria-label={STATE_TYPE_LABELS[type]}
      className={cn('size-4 shrink-0', type === 'canceled' && 'text-fg-muted', className)}
    />
  )
}

const PRIORITY_ICONS = {
  0: Minus,
  1: OctagonAlert,
  2: SignalHigh,
  3: SignalMedium,
  4: SignalLow,
} as const

export function PriorityIcon({ priority, className }: { priority: number; className?: string }) {
  const Icon = PRIORITY_ICONS[priority as keyof typeof PRIORITY_ICONS] ?? Minus
  return (
    <Icon
      role="img"
      aria-label={PRIORITY_LABELS[priority] ?? 'Приоритет'}
      strokeWidth={priority === 1 ? 2.75 : 2}
      className={cn('size-4 shrink-0', priority === 0 && 'text-fg-muted', className)}
    />
  )
}

/** Инициалы исполнителя — короче имени и не требуют аватара. */
export function Avatar({ name, className }: { name: string; className?: string }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
  return (
    <span
      title={name}
      className={cn(
        'border-border bg-surface-hover grid size-6 shrink-0 place-items-center rounded-full border text-[10px] font-semibold',
        className,
      )}
    >
      <span aria-hidden="true">{initials || '?'}</span>
      <span className="sr-only">{name}</span>
    </span>
  )
}
