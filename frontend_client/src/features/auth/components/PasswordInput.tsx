import { Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import type { ComponentProps } from 'react'

import { Input } from '@/shared/ui/Input'

/**
 * Поле пароля с показом введённого.
 *
 * Поле подтверждения не нужно: увидеть, что набрал, — тот же способ поймать
 * опечатку, но без второй половины формы.
 */
export function PasswordInput(props: ComponentProps<typeof Input>) {
  const [visible, setVisible] = useState(false)
  const Icon = visible ? EyeOff : Eye

  return (
    <div className="relative">
      <Input {...props} type={visible ? 'text' : 'password'} className="pr-10" />
      <button
        type="button"
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? 'Скрыть пароль' : 'Показать пароль'}
        className="text-fg-muted hover:text-fg focus-visible:outline-accent absolute top-0 right-0 flex h-10 w-10 items-center justify-center rounded-md transition focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        <Icon aria-hidden="true" className="size-4" />
      </button>
    </div>
  )
}
