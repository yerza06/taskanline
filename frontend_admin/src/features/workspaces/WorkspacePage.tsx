import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useCan } from '@/app/session'
import { adminFetch } from '@/shared/api/admin'
import { humanMessage } from '@/shared/api/messages'
import type { AdminWorkspaceDetail } from '@/shared/api/types'
import { formatDateTime } from '@/shared/lib/format'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'
import { PageTitle, Section, TD, TH, Table } from '@/shared/ui/Page'

/**
 * Карточка пространства: участники и роли. Задач, проектов и их описаний здесь нет —
 * чтобы заглянуть внутрь, superadmin назначает себя владельцем, и это видно всем.
 */
export function WorkspacePage({ workspaceId }: { workspaceId: string }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const canAdmin = useCan('admin')
  const canSuper = useCan('superadmin')
  const [deleting, setDeleting] = useState(false)
  const [granting, setGranting] = useState(false)
  const [typed, setTyped] = useState('')
  const space = useQuery({
    queryKey: ['workspace', workspaceId],
    queryFn: () => adminFetch<AdminWorkspaceDetail>(`/workspaces/${workspaceId}`),
  })
  const remove = useMutation({
    mutationFn: () => adminFetch<void>(`/workspaces/${workspaceId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['workspaces'] })
      await navigate({ to: '/workspaces' })
    },
  })
  const grant = useMutation({
    mutationFn: () =>
      adminFetch<AdminWorkspaceDetail>(`/workspaces/${workspaceId}/grant-ownership`, { method: 'POST' }),
    onSuccess: (detail) => {
      queryClient.setQueryData(['workspace', workspaceId], detail)
      setGranting(false)
    },
  })

  if (space.isError) return <Alert>{humanMessage(space.error)}</Alert>
  if (!space.data) return null
  const data = space.data

  return (
    <>
      <PageTitle
        title={data.name}
        hint={`/${data.slug} · создано ${formatDateTime(data.created_at)} · задач ${data.tasks} · команд ${data.teams}`}
      />
      {(remove.error ?? grant.error) && <Alert className="mb-4">{humanMessage(remove.error ?? grant.error)}</Alert>}
      <Section title={`Участники · ${data.members}`}>
        <Table label="Участники">
          <thead>
            <tr>
              <th className={TH}>Email</th>
              <th className={TH}>Имя</th>
              <th className={TH}>Роль</th>
            </tr>
          </thead>
          <tbody>
            {data.member_list.map((member) => (
              <tr key={member.user_id}>
                <td className={TD}>
                  <Link to="/users/$userId" params={{ userId: member.user_id }} className="hover:underline">
                    {member.email}
                  </Link>
                </td>
                <td className={TD}>{member.full_name}</td>
                <td className={member.role === 'owner' ? `${TD} font-semibold` : TD}>{member.role}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Section>

      {canAdmin && (
        <div className="mt-6 flex flex-wrap gap-2" role="group" aria-label="Действия">
          {canSuper && (
            <Button variant="secondary" onClick={() => setGranting(true)}>
              Назначить себя владельцем
            </Button>
          )}
          <Button variant="danger" className="ml-auto" onClick={() => setDeleting(true)}>
            Удалить пространство
          </Button>
        </div>
      )}

      <Dialog
        open={granting}
        onOpenChange={setGranting}
        title="Аварийная передача владения"
        description="Вы станете владельцем и увидите содержимое. Действие попадёт в журнал, а нынешние владельцы получат уведомление."
      >
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setGranting(false)}>
            Отмена
          </Button>
          <Button disabled={grant.isPending} onClick={() => grant.mutate()}>
            Назначить
          </Button>
        </div>
      </Dialog>

      <Dialog
        open={deleting}
        onOpenChange={(open) => {
          setDeleting(open)
          setTyped('')
        }}
        title={`Удалить «${data.name}»?`}
        description="Пространство исчезнет со всеми командами, проектами и задачами. Вернуть нельзя."
      >
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            setDeleting(false)
            remove.mutate()
          }}
        >
          {/* Подтверждение, которое нельзя прокликать не глядя (админ-спека §7). */}
          <Field label={`Введите название пространства: ${data.name}`}>
            {(control) => (
              <Input {...control} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDeleting(false)}>
              Отмена
            </Button>
            <Button type="submit" variant="danger" disabled={typed !== data.name || remove.isPending}>
              Удалить навсегда
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  )
}
