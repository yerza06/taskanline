import type { ReactNode } from 'react'
import { useId } from 'react'

interface FieldControlProps {
  id: string
  'aria-invalid': boolean
  'aria-describedby': string | undefined
}

interface FieldProps {
  label: string
  error?: string
  hint?: string
  children: (control: FieldControlProps) => ReactNode
}

/**
 * Подпись, поле и сообщение об ошибке как одно целое.
 *
 * Поле получает атрибуты доступности не по желанию автора экрана, а всегда:
 * связь `aria-describedby` с текстом ошибки легко забыть и невозможно заметить
 * глазами — её видно только скринридером.
 */
export function Field({ label, error, hint, children }: FieldProps) {
  const id = useId()
  const errorId = `${id}-error`
  const hintId = `${id}-hint`
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ')

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-fg block text-sm font-medium">
        {label}
      </label>

      {children({
        id,
        'aria-invalid': Boolean(error),
        'aria-describedby': describedBy || undefined,
      })}

      {hint && (
        <p id={hintId} className="text-fg-muted text-xs">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-danger text-xs">
          {error}
        </p>
      )}
    </div>
  )
}
