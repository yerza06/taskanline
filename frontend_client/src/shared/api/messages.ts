/**
 * Перевод машиночитаемого `code` в текст для человека.
 *
 * Тексты бэкенда написаны для разработчика и SDK; на экране нужен ответ на
 * вопрос «что мне теперь делать». Незнакомый код показывается как есть —
 * молчаливое «что-то пошло не так» хуже любого точного сообщения.
 */

import { ApiError } from './client'

const MESSAGES: Record<string, string> = {
  unauthorized: 'Нужно войти заново',
  invalid_token: 'Сессия истекла, войдите заново',
  invalid_credentials: 'Неверный email или пароль',
  email_already_registered: 'Этот email уже зарегистрирован',
  token_reuse_detected: 'Сессия закрыта из соображений безопасности, войдите заново',
  insufficient_scope: 'Токену не хватает прав на изменение',
  csrf_required: 'Запрос отклонён защитой от подделки. Обновите страницу',
  token_not_found: 'Токен уже отозван',
  user_not_found: 'Пользователь не найден',
  validation_error: 'Проверьте заполненные поля',
  internal_error: 'Внутренняя ошибка сервера. Попробуйте ещё раз',
}

function retryAfter(error: ApiError): number {
  const value = error.details.retry_after
  return typeof value === 'number' && Number.isFinite(value) ? Math.ceil(value) : 0
}

export function humanMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    // Сюда попадает TypeError от fetch: сети нет или сервер не отвечает.
    return 'Сервер недоступен. Проверьте соединение'
  }

  if (error.code === 'rate_limited') {
    const seconds = retryAfter(error)
    return seconds > 0
      ? `Слишком много попыток. Повторите через ${seconds} с`
      : 'Слишком много попыток. Повторите позже'
  }

  return MESSAGES[error.code] ?? error.message
}

interface ValidationDetail {
  loc: (string | number)[]
  msg: string
}

/**
 * Ошибки валидации по именам полей формы.
 *
 * FastAPI отдаёт путь целиком (`["body", "email"]`); форме нужно последнее
 * строковое звено — имя поля.
 */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || error.code !== 'validation_error') {
    return {}
  }

  const errors = error.details.errors
  if (!Array.isArray(errors)) {
    return {}
  }

  const result: Record<string, string> = {}
  for (const detail of errors as ValidationDetail[]) {
    const field = [...detail.loc].reverse().find((part) => typeof part === 'string' && part !== 'body')
    if (typeof field === 'string') {
      result[field] = detail.msg
    }
  }
  return result
}
