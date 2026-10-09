import { useState } from 'react'

import { canWrite, useSession } from '@/features/auth/api/session'
import {
  useChangeRole,
  useInvitations,
  useInvite,
  useMembers,
  useRemoveMember,
  useRevokeInvitation,
  type MemberLevel,
} from '@/features/members/api/members'
import { ROLE_TEXT, ROLES } from '@/features/members/model/roles'
import { humanMessage } from '@/shared/api/messages'
import { formatDateTime } from '@/shared/lib/format'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Input } from '@/shared/ui/Input'
import { Select } from '@/shared/ui/Select'

/**
 * Участники одного уровня — пространства, команды или проекта — и приглашение.
 *
 * Кнопки не прячутся по роли заранее: права проверяет сервер, и его 403 доходит
 * до человека понятным текстом. Прятать — значит дублировать матрицу прав на клиенте.
 */
export function MembersPanel({
  level,
  id,
  workspaceId,
}: {
  level: MemberLevel
  id: string
  workspaceId: string
}) {
  const writable = canWrite(useSession())
  const session = useSession()
  const members = useMembers(level, id)
  const change = useChangeRole(level, id)
  const remove = useRemoveMember(level, id)
  const invite = useInvite(workspaceId)
  const invitations = useInvitations(workspaceId).data ?? []
  const revoke = useRevokeInvitation(workspaceId)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState(Object.keys(ROLES[level])[1] ?? 'member')
  const [sent, setSent] = useState<string | null>(null)
  const pending = invitations.filter(
    (item) => item.scope_type === level && item.scope_id === id && item.status === 'pending',
  )
  const error = change.error ?? remove.error ?? revoke.error

  return (
    <div className="space-y-6">
      {error && <Alert>{humanMessage(error)}</Alert>}
      <ul className="divide-border border-border divide-y rounded-md border">
        {(members.data ?? []).map((member) => (
          <li key={member.user_id} className="flex flex-wrap items-center gap-3 px-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm">
                {member.full_name}
                {member.user_id === session?.id && <span className="text-fg-muted"> (вы)</span>}
              </p>
              <p className="text-fg-muted truncate text-xs">{member.email}</p>
            </div>
            {member.role === 'owner' || !writable ? (
              <span className="text-fg-muted text-sm">{ROLE_TEXT[member.role] ?? member.role}</span>
            ) : (
              <Select
                aria-label={`Роль: ${member.full_name}`}
                value={member.role}
                onChange={(e) => change.mutate({ userId: member.user_id, role: e.target.value })}
              >
                {Object.entries(ROLES[level]).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            )}
            {writable && member.role !== 'owner' && (
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Исключить ${member.full_name}`}
                onClick={() => remove.mutate(member.user_id)}
              >
                Исключить
              </Button>
            )}
          </li>
        ))}
      </ul>

      {writable && (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault()
            setSent(null)
            invite.mutate(
              { email: email.trim(), scope_type: level, scope_id: id, role },
              {
                onSuccess: (item) => {
                  setSent(item.email)
                  setEmail('')
                },
              },
            )
          }}
        >
          <h3 className="text-sm font-medium">Пригласить по email</h3>
          <div className="flex flex-wrap gap-2">
            <Input
              aria-label="Email приглашённого"
              type="email"
              required
              placeholder="name@example.com"
              className="h-9 w-64"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Select aria-label="Роль приглашённого" value={role} onChange={(e) => setRole(e.target.value)}>
              {Object.entries(ROLES[level]).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            <Button type="submit" size="sm" disabled={invite.isPending}>
              Пригласить
            </Button>
          </div>
          {invite.error && <Alert>{humanMessage(invite.error)}</Alert>}
          {sent && (
            <p role="status" className="text-fg-muted text-sm">
              Приглашение отправлено на {sent}.
            </p>
          )}
        </form>
      )}

      {pending.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Ждут ответа</h3>
          <ul className="divide-border border-border divide-y rounded-md border">
            {pending.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate">{item.email}</span>
                <span className="text-fg-muted">{ROLE_TEXT[item.role] ?? item.role}</span>
                <span className="text-fg-muted text-xs">до {formatDateTime(item.expires_at)}</span>
                {writable && (
                  <Button size="sm" variant="ghost" onClick={() => revoke.mutate(item.id)}>
                    Отозвать
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
