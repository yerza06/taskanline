import { HttpResponse, http, type HttpHandler } from 'msw'

import type {
  AdminSession,
  AdminUserDetail,
  AdminUserRow,
  AdminWorkspaceDetail,
  AuditEntry,
  SettingsRead,
  Stats,
} from '@/shared/api/types'

const AT = '2026-10-08T10:00:00Z'
export const ROOT_ID = '019a5c1e-0000-7000-8000-000000000001'
export const USER_ID = '019a5c1e-0000-7000-8000-000000000002'
export const WS_ID = '019a5c1e-0000-7000-8000-0000000000a0'

export const SESSION: AdminSession = {
  user_id: ROOT_ID,
  email: 'root@example.com',
  full_name: 'Ольга Владелец',
  role: 'superadmin',
  reauth_until: null,
}

export const STATS: Stats = {
  users: { total: 3, active: 2, blocked: 1, deleted: 0 },
  workspaces: 2,
  teams: 3,
  tasks: 41,
  version: '0.1.0',
  migration: '0006_admin',
  migration_head: '0006_admin',
}

export const USER_ROW: AdminUserRow = {
  id: USER_ID,
  email: 'leaver@example.com',
  full_name: 'Пётр Уходящий',
  role: 'user',
  status: 'active',
  created_at: AT,
  last_seen_at: AT,
}

export const USER: AdminUserDetail = {
  ...USER_ROW,
  memberships: [{ workspace_id: WS_ID, workspace_name: 'Acme', workspace_slug: 'acme', role: 'member' }],
  tokens: [
    {
      id: '019a5c1e-0000-7000-8000-0000000000f1',
      name: 'claude-code',
      prefix: 'tkl_abcdefgh',
      scope: 'read_write',
      created_at: AT,
      last_used_at: null,
      expires_at: null,
      revoked_at: null,
    },
  ],
  logins: [{ kind: 'password', ip: '10.0.0.7', user_agent: 'Firefox', created_at: AT }],
}

export const WORKSPACE: AdminWorkspaceDetail = {
  id: WS_ID,
  name: 'Acme',
  slug: 'acme',
  owners: [{ user_id: ROOT_ID, email: 'root@example.com' }],
  members: 2,
  teams: 1,
  tasks: 41,
  created_at: AT,
  last_activity_at: AT,
  member_list: [
    { user_id: ROOT_ID, email: 'root@example.com', full_name: 'Ольга', role: 'owner' },
    { user_id: USER_ID, email: 'leaver@example.com', full_name: 'Пётр', role: 'member' },
  ],
}

export const SETTINGS: SettingsRead = {
  instance_name: 'TasKanLine',
  registration_mode: 'invite_only',
  allowed_email_domains: [],
  invitation_ttl_days: 7,
  maintenance_mode: false,
  updated_by: null,
  updated_at: AT,
}

export const ENTRY: AuditEntry = {
  id: '019a5c1e-0000-7000-8000-0000000000e1',
  actor: { id: ROOT_ID, email: 'root@example.com', full_name: 'Ольга' },
  action: 'user_blocked',
  target_type: 'user',
  target_id: USER_ID,
  payload: { email: 'leaver@example.com' },
  ip: '10.0.0.1',
  user_agent: 'Firefox',
  created_at: AT,
}

export function errorBody(code: string, message = 'Ошибка', details: object = {}) {
  return { error: { code, message, details } }
}

const page = <T,>(items: T[]) => ({ items, next_cursor: null, has_more: false })

export function defaultHandlers(): HttpHandler[] {
  return [
    http.post('/api/v1/admin/session', () => HttpResponse.json(SESSION)),
    http.get('/api/v1/admin/stats', () => HttpResponse.json(STATS)),
    http.get('/api/v1/admin/audit', () => HttpResponse.json(page([ENTRY]))),
    http.get('/api/v1/admin/users', () => HttpResponse.json(page([USER_ROW]))),
    http.get('/api/v1/admin/users/:id', () => HttpResponse.json(USER)),
    http.get('/api/v1/admin/workspaces', () => HttpResponse.json(page([WORKSPACE]))),
    http.get('/api/v1/admin/workspaces/:id', () => HttpResponse.json(WORKSPACE)),
    http.get('/api/v1/admin/settings', () => HttpResponse.json(SETTINGS)),
  ]
}
