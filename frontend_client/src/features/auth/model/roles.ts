import type { InstanceRole } from '@/shared/api/types'

/** Роль инстанса на языке интерфейса. Значения приходят из CHECK-ограничения в БД. */
export const ROLE_LABELS: Record<InstanceRole, string> = {
  superadmin: 'Суперадминистратор',
  admin: 'Администратор',
  support: 'Поддержка',
  user: 'Пользователь',
}
