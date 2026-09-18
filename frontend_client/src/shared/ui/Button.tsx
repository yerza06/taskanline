import { cva, type VariantProps } from 'class-variance-authority'
import type { ButtonHTMLAttributes } from 'react'

import { cn } from '@/shared/lib/cn'

/**
 * Кнопка приложения.
 *
 * Компонент из shadcn/ui перенесён руками и переписан на семантические токены
 * проекта: своя палитра уже задана в index.css, и второй словарь цветов рядом
 * с ней разошёлся бы с первым при первой же правке темы.
 */
const button = cva(
  'inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition ' +
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ' +
    'disabled:cursor-not-allowed disabled:opacity-60',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-accent-fg hover:opacity-90',
        secondary: 'border-border bg-surface hover:bg-surface-hover border',
        ghost: 'hover:bg-surface-hover',
        // Палитра чёрно-белая, и опасность нельзя показать цветом. Её показывает
        // вес: полная по светлоте граница, полужирный текст и инверсия под курсором.
        danger: 'border-danger text-danger hover:bg-danger hover:text-accent-fg border font-semibold',
      },
      size: {
        sm: 'h-8 px-3',
        md: 'h-10 px-4',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof button>

export function Button({ className, variant, size, type = 'button', ...props }: ButtonProps) {
  // type по умолчанию `button`: кнопка внутри формы без него отправляет её.
  return <button type={type} className={cn(button({ variant, size }), className)} {...props} />
}
