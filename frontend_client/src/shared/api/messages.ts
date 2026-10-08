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
  invitation_not_found: 'Приглашение не найдено или отозвано',
  invitation_not_pending: 'Приглашение уже недействительно',
  invitation_email_mismatch: 'Приглашение отправлено на другой адрес',
  login_required: 'Учётная запись с этим адресом уже есть — войдите, чтобы принять приглашение',
  registration_required: 'Укажите имя и пароль',
  insufficient_role: 'Недостаточно прав для этого действия',
  workspace_slug_taken: 'Этот адрес пространства уже занят',
  team_key_taken: 'Команда с таким ключом уже есть',
  state_name_taken: 'Статус с таким названием уже есть',
  label_name_taken: 'Метка с таким названием уже есть',
  state_is_default: 'Статус по умолчанию нельзя удалить — сначала назначьте другой',
  invitation_exists: 'Этот человек уже приглашён',
  already_member: 'Этот человек уже участник',
  last_owner: 'Нельзя оставить пространство без владельца',
  relation_exists: 'Такая связь уже есть',
  relation_self: 'Задачу нельзя связать с ней самой',
  relation_cycle: 'Связь замкнула бы цепочку блокировок',
  parent_cycle: 'Задача не может быть подзадачей своей подзадачи',
  parent_depth_exceeded: 'Слишком глубокая вложенность подзадач',
  task_not_found: 'Задача не найдена',
  target_not_found: 'Задача не найдена',
  parent_not_found: 'Родительская задача не найдена',
  task_key_ambiguous: 'Ключ задачи встречается в нескольких пространствах',
  view_not_found: 'View не найден',
  not_comment_author: 'Менять можно только свои комментарии',
  invalid_filter: 'Фильтр не по правилам — проверьте условия',
  registration_closed: 'Регистрация на этом сервере только по приглашению',
  reset_token_invalid: 'Ссылка недействительна или устарела — запросите новую',
  maintenance: 'Сервер на обслуживании, попробуйте позже',
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
