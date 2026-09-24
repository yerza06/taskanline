import type { InvitationPreview } from '@/shared/api/types'

/** `lead` и `viewer` в письме человеку ничего не скажут. */
const ROLES: Record<string, string> = {
  admin: 'администратор',
  member: 'участник',
  guest: 'гость',
  lead: 'руководитель команды',
  viewer: 'наблюдатель',
}

const SCOPES: Record<InvitationPreview['scope_type'], string> = {
  workspace: 'всё рабочее пространство',
  team: 'одна команда',
  project: 'один проект',
}

export function roleLabel(role: string): string {
  return ROLES[role] ?? role
}

export function scopeLabel(scope: InvitationPreview['scope_type']): string {
  return SCOPES[scope]
}

/** Почему по ссылке больше нельзя войти. */
export const CLOSED: Record<Exclude<InvitationPreview['status'], 'pending'>, string> = {
  accepted: 'Приглашение уже принято.',
  expired: 'Срок приглашения истёк — попросите прислать новое.',
  revoked: 'Приглашение отозвано.',
}
