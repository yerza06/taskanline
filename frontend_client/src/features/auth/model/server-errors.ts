import type { Path, UseFormSetError } from 'react-hook-form'

import { fieldErrors, humanMessage } from '@/shared/api/messages'

/**
 * Ответ сервера, разложенный по форме.
 *
 * Ошибки валидации (422) ложатся на поля, всё остальное — в общее сообщение
 * над формой: «email: value is not a valid email address» под кнопкой «Войти»
 * не помогает никому.
 */
export function applyServerError<Values extends Record<string, unknown>>(
  error: unknown,
  setError: UseFormSetError<Values>,
  known: readonly (keyof Values & string)[],
): string | null {
  const byField = fieldErrors(error)
  const matched = known.filter((name) => byField[name])

  for (const name of matched) {
    setError(name as Path<Values>, { type: 'server', message: byField[name] })
  }

  return matched.length > 0 ? null : humanMessage(error)
}
