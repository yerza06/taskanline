import type { AuditAction, InstanceRole, RegistrationMode } from '@/shared/api/types'

export const ROLE_LABELS: Record<InstanceRole, string> = {
  superadmin: 'Суперадминистратор',
  admin: 'Администратор',
  support: 'Поддержка',
  user: 'Пользователь',
}

export const STATUS_LABELS: Record<string, string> = {
  active: 'Активен',
  blocked: 'Заблокирован',
  deleted: 'Удалён',
}

export const ACTION_LABELS: Record<AuditAction, string> = {
  admin_login: 'Вход в админку',
  reauth_failed: 'Неверный пароль при подтверждении',
  user_blocked: 'Пользователь заблокирован',
  user_unblocked: 'Пользователь разблокирован',
  user_role_changed: 'Смена роли инстанса',
  user_deleted: 'Пользователь удалён',
  password_reset_sent: 'Отправлена ссылка на смену пароля',
  token_revoked: 'Отозван токен агента',
  workspace_deleted: 'Пространство удалено',
  workspace_ownership_granted: 'Аварийная передача владения',
  settings_changed: 'Изменены настройки инстанса',
}

export const MODE_LABELS: Record<RegistrationMode, string> = {
  invite_only: 'Только по приглашению',
  open: 'Открытая',
  domain_allowlist: 'По доменам почты',
}
