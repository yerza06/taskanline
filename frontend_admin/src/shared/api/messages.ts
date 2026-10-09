import { ApiError } from './client'

/** Код ошибки API → текст для дежурного администратора. */
const MESSAGES: Record<string, string> = {
  insufficient_role: 'Недостаточно прав: действие доступно роли выше вашей',
  reauth_required: 'Подтвердите действие паролем',
  reauth_failed: 'Неверный пароль',
  session_terminated: 'Три неверных пароля подряд — сессия закрыта, войдите заново',
  last_superadmin: 'Это последний действующий superadmin — сначала назначьте другого',
  last_owner_of_workspace:
    'Пользователь — единственный владелец пространств; сначала передайте владение',
  user_deleted: 'Учётная запись уже удалена',
  user_not_found: 'Пользователь не найден',
  workspace_not_found: 'Пространство не найдено',
  token_not_found: 'Токен не найден',
  validation_error: 'Проверьте заполненные поля',
  session_required: 'Админ-панель принимает только сессию человека',
}

export function humanMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Сервер недоступен. Проверьте соединение'
  return MESSAGES[error.code] ?? error.message
}
