import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'

import { useCan } from '@/app/session'
import { adminFetch } from '@/shared/api/admin'
import { humanMessage } from '@/shared/api/messages'
import type { AdminUserDetail, InstanceRole } from '@/shared/api/types'
import { formatDateTime } from '@/shared/lib/format'
import { ROLE_LABELS, STATUS_LABELS } from '@/shared/lib/labels'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { PageTitle, Section, TD, TH, Table } from '@/shared/ui/Page'
import { Select } from '@/shared/ui/Select'

const LOGIN_KINDS: Record<string, string> = {
  password: 'Пароль',
  registration: 'Регистрация',
  invitation: 'Приглашение',
  password_reset: 'Сброс пароля',
}

/**
 * Карточка пользователя: профиль, членства, токены агентов, входы — и действия.
 * Опасные (удаление) отделены от обычных и требуют подтверждения.
 */
export function UserPage({ userId }: { userId: string }) {
  const queryClient = useQueryClient()
  const canAdmin = useCan('admin')
  const canSuper = useCan('superadmin')
  const [notice, setNotice] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const user = useQuery({
    queryKey: ['user', userId],
    queryFn: () => adminFetch<AdminUserDetail>(`/users/${userId}`),
  })

  const action = useMutation({
    mutationFn: ({ path, method = 'POST', json }: { path: string; method?: 'POST' | 'PATCH' | 'DELETE'; json?: unknown; done?: string }) =>
      adminFetch(`/users/${userId}${path}`, { method, json }),
    onSuccess: async (_, variables) => {
      setNotice(variables.done ?? null)
      await queryClient.invalidateQueries({ queryKey: ['user', userId] })
      await queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  if (user.isError) return <Alert>{humanMessage(user.error)}</Alert>
  if (!user.data) return null
  const data = user.data
  const deleted = data.status === 'deleted'

  return (
    <>
      <PageTitle
        title={data.full_name}
        hint={`${data.email} · ${ROLE_LABELS[data.role]} · ${STATUS_LABELS[data.status]}`}
        actions={
          <Link
            to="/audit"
            search={{ target_id: data.id }}
            className="text-sm underline underline-offset-4"
          >
            Журнал по этому пользователю
          </Link>
        }
      />
      {action.error && <Alert className="mb-4">{humanMessage(action.error)}</Alert>}
      {notice && (
        <p role="status" className="border-border mb-4 rounded-md border px-3 py-2 text-sm">
          {notice}
        </p>
      )}

      {canAdmin && !deleted && (
        <div className="mb-6 flex flex-wrap items-center gap-2" role="group" aria-label="Действия">
          {data.status === 'active' ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => action.mutate({ path: '/block', done: 'Заблокирован: сессии и токены отозваны.' })}
            >
              Заблокировать
            </Button>
          ) : (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => action.mutate({ path: '/unblock', done: 'Разблокирован.' })}
            >
              Разблокировать
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              action.mutate({ path: '/reset-password', done: `Ссылка на смену пароля отправлена на ${data.email}.` })
            }
          >
            Отправить ссылку на смену пароля
          </Button>
          {canSuper && (
            <label className="flex items-center gap-2 text-sm">
              Роль
              <Select
                aria-label="Роль инстанса"
                value={data.role}
                onChange={(e) =>
                  action.mutate({
                    path: '/role',
                    method: 'PATCH',
                    json: { role: e.target.value as InstanceRole },
                    done: 'Роль изменена.',
                  })
                }
              >
                {(Object.keys(ROLE_LABELS) as InstanceRole[]).map((value) => (
                  <option key={value} value={value}>
                    {ROLE_LABELS[value]}
                  </option>
                ))}
              </Select>
            </label>
          )}
          {canSuper && (
            <Button variant="danger" size="sm" className="ml-auto" onClick={() => setDeleting(true)}>
              Удалить учётную запись
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Рабочие пространства">
          {data.memberships.length === 0 ? (
            <p className="text-fg-muted text-sm">Ни в одном.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {data.memberships.map((m) => (
                <li key={m.workspace_id}>
                  <Link
                    to="/workspaces/$workspaceId"
                    params={{ workspaceId: m.workspace_id }}
                    className="underline-offset-2 hover:underline"
                  >
                    {m.workspace_name}
                  </Link>{' '}
                  <span className="text-fg-muted">
                    /{m.workspace_slug} · {m.role}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="Последние входы">
          {data.logins.length === 0 ? (
            <p className="text-fg-muted text-sm">Входов не было.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {data.logins.map((login) => (
                <li key={login.created_at} className="flex flex-wrap gap-x-2">
                  <span>{formatDateTime(login.created_at)}</span>
                  <span className="text-fg-muted">
                    {LOGIN_KINDS[login.kind]} · {login.ip ?? 'адрес неизвестен'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <div className="mt-4">
        <Section title="Токены агентов">
          <Table label="Токены агентов">
            <thead>
              <tr>
                <th className={TH}>Название</th>
                <th className={TH}>Префикс</th>
                <th className={TH}>Права</th>
                <th className={TH}>Использован</th>
                <th className={TH}>Состояние</th>
                <th className={TH} />
              </tr>
            </thead>
            <tbody>
              {data.tokens.map((token) => (
                <tr key={token.id}>
                  <td className={TD}>{token.name}</td>
                  <td className={TD}>
                    <code>{token.prefix}</code>
                  </td>
                  <td className={TD}>{token.scope === 'read' ? 'чтение' : 'чтение и запись'}</td>
                  <td className={`${TD} text-fg-muted`}>
                    {token.last_used_at ? formatDateTime(token.last_used_at) : 'не использован'}
                  </td>
                  <td className={TD}>{token.revoked_at ? 'отозван' : 'действует'}</td>
                  <td className={TD}>
                    {canAdmin && !token.revoked_at && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          action.mutate({ path: `/tokens/${token.id}`, method: 'DELETE', done: 'Токен отозван.' })
                        }
                      >
                        Отозвать
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          {data.tokens.length === 0 && <p className="text-fg-muted text-sm">Токенов нет.</p>}
        </Section>
      </div>

      <Dialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Удалить ${data.email}?`}
        description="Учётная запись будет анонимизирована: задачи и комментарии останутся, автором станет «Удалённый пользователь». Вернуть нельзя."
      >
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDeleting(false)}>
            Отмена
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              setDeleting(false)
              action.mutate({ path: '', method: 'DELETE', done: 'Учётная запись удалена.' })
            }}
          >
            Удалить
          </Button>
        </div>
      </Dialog>
    </>
  )
}
