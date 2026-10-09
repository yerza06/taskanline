import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Склейка классов с разрешением конфликтов Tailwind.
 *
 * Без `twMerge` переданный снаружи `px-6` не перебьёт `px-3` внутри компонента,
 * а просто встанет рядом — и выиграет тот, кто оказался позже в CSS.
 */
export function cn(...values: ClassValue[]): string {
  return twMerge(clsx(values))
}
