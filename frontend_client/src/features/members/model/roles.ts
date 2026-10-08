import type { MemberLevel } from '@/features/members/api/members'

/** Роли, которые можно выдать на уровне, — те же, что разрешает бэкенд. */
export const ROLES: Record<MemberLevel, Record<string, string>> = {
  workspace: { admin: 'Администратор', member: 'Участник', guest: 'Гость' },
  team: { lead: 'Лид', member: 'Участник' },
  project: { admin: 'Администратор', member: 'Участник', viewer: 'Наблюдатель' },
}

export const ROLE_TEXT: Record<string, string> = {
  owner: 'Владелец',
  ...ROLES.workspace,
  ...ROLES.team,
  ...ROLES.project,
}

