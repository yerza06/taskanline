import { useParams } from '@tanstack/react-router'
import { useState, type ReactNode } from 'react'

import { canWrite, useSession } from '@/features/auth/api/session'
import { MembersPanel } from '@/features/members/components/MembersPanel'
import { StateIcon } from '@/features/tasks/components/TaskIcons'
import { STATE_TYPE_LABELS, STATE_TYPES } from '@/features/tasks/model/labels'
import {
  useCreateLabel,
  useCreateState,
  useDeleteLabel,
  useDeleteState,
  useLabels,
  useStates,
  useTeamByKey,
  useUpdateState,
} from '@/features/teams/api/teams'
import { useCurrentWorkspace } from '@/features/workspaces/api/workspaces'
import { humanMessage } from '@/shared/api/messages'
import type { StateRead, StateType, TeamRead } from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { Input } from '@/shared/ui/Input'
import { Select } from '@/shared/ui/Select'

/**
 * Цвет статусов и меток хранится в API (его видят CLI и интеграции), но интерфейс
 * чёрно-белый и его не показывает — поэтому новым объектам ставится нейтральный серый.
 */
const NEUTRAL = '#808080'

function Card({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <section className="border-border bg-surface space-y-4 rounded-lg border p-4 sm:p-6">
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="text-fg-muted text-sm">{hint}</p>
      </div>
      {children}
    </section>
  )
}

function States({ team, writable }: { team: TeamRead; writable: boolean }) {
  const states = useStates(team.id).data ?? []
  const create = useCreateState(team.id)
  const update = useUpdateState(team.id)
  const remove = useDeleteState(team.id)
  const [name, setName] = useState('')
  const [type, setType] = useState<StateType>('unstarted')
  const [deleting, setDeleting] = useState<StateRead | null>(null)
  const [moveTo, setMoveTo] = useState('')
  const error = create.error ?? update.error

  function shift(state: StateRead, delta: number) {
    const target = states.indexOf(state) + delta
    if (target < 0 || target >= states.length) return
    update.mutate({ id: state.id, position: states[target]?.position ?? target })
  }

  return (
    <Card title="Статусы" hint="Колонки доски по порядку. Тип статуса задаёт смысл: в работе, завершена…">
      {error && <Alert>{humanMessage(error)}</Alert>}
      <ol className="divide-border border-border divide-y rounded-md border">
        {states.map((state, index) => (
          <li key={state.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
            <StateIcon type={state.type} />
            <span className="min-w-0 flex-1 truncate">
              {state.name}
              {state.is_default && <span className="text-fg-muted"> · по умолчанию</span>}
            </span>
            <span className="text-fg-muted text-xs">{STATE_TYPE_LABELS[state.type]}</span>
            {writable && (
              <>
                <Button size="sm" variant="ghost" aria-label={`Выше: ${state.name}`} disabled={index === 0} onClick={() => shift(state, -1)}>
                  ↑
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Ниже: ${state.name}`}
                  disabled={index === states.length - 1}
                  onClick={() => shift(state, 1)}
                >
                  ↓
                </Button>
                {!state.is_default && (
                  <Button size="sm" variant="ghost" onClick={() => update.mutate({ id: state.id, is_default: true })}>
                    По умолчанию
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Удалить статус ${state.name}`}
                  onClick={() => {
                    setDeleting(state)
                    setMoveTo(states.find((s) => s.id !== state.id)?.id ?? '')
                  }}
                >
                  Удалить
                </Button>
              </>
            )}
          </li>
        ))}
      </ol>
      {writable && (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (!name.trim()) return
            create.mutate({ name: name.trim(), type, color: NEUTRAL, is_default: false }, { onSuccess: () => setName('') })
          }}
        >
          <Input aria-label="Название статуса" placeholder="Например, На ревью" className="h-9 w-56" value={name} onChange={(e) => setName(e.target.value)} />
          <Select aria-label="Тип статуса" value={type} onChange={(e) => setType(e.target.value as StateType)}>
            {STATE_TYPES.map((value) => (
              <option key={value} value={value}>
                {STATE_TYPE_LABELS[value]}
              </option>
            ))}
          </Select>
          <Button type="submit" size="sm" disabled={create.isPending}>
            Добавить статус
          </Button>
        </form>
      )}
      <Dialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Удалить статус «${deleting?.name ?? ''}»?`}
        description="Задачи этого статуса переедут в выбранный."
      >
        {remove.error && <Alert className="mb-3">{humanMessage(remove.error)}</Alert>}
        <div className="space-y-3">
          <Select aria-label="Куда перенести задачи" className="w-full" value={moveTo} onChange={(e) => setMoveTo(e.target.value)}>
            {states
              .filter((s) => s.id !== deleting?.id)
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
          </Select>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDeleting(null)}>
              Отмена
            </Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() =>
                deleting && remove.mutate({ id: deleting.id, moveTo }, { onSuccess: () => setDeleting(null) })
              }
            >
              Удалить
            </Button>
          </div>
        </div>
      </Dialog>
    </Card>
  )
}

function Labels({ team, workspaceId, writable }: { team: TeamRead; workspaceId: string; writable: boolean }) {
  const labels = useLabels(workspaceId, team.id).data ?? []
  const create = useCreateLabel(workspaceId)
  const remove = useDeleteLabel(workspaceId)
  const [name, setName] = useState('')
  const [shared, setShared] = useState(false)
  return (
    <Card title="Метки" hint="Метки команды и общие метки пространства.">
      {(create.error ?? remove.error) && <Alert>{humanMessage(create.error ?? remove.error)}</Alert>}
      <ul className="flex flex-wrap gap-2">
        {labels.map((label) => (
          <li key={label.id} className="border-border flex items-center gap-1 rounded-full border py-0.5 pr-1 pl-2 text-sm">
            {label.name}
            {label.team_id === null && <span className="text-fg-muted text-xs">· общая</span>}
            {writable && (
              <button
                type="button"
                aria-label={`Удалить метку ${label.name}`}
                onClick={() => remove.mutate(label.id)}
                className="text-fg-muted hover:text-fg rounded-full px-1"
              >
                ×
              </button>
            )}
          </li>
        ))}
        {labels.length === 0 && <li className="text-fg-muted text-sm">Меток пока нет.</li>}
      </ul>
      {writable && (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (!name.trim()) return
            create.mutate(
              { name: name.trim(), color: NEUTRAL, team_id: shared ? null : team.id },
              { onSuccess: () => setName('') },
            )
          }}
        >
          <Input aria-label="Название метки" placeholder="bug" className="h-9 w-48" value={name} onChange={(e) => setName(e.target.value)} />
          <label className="flex items-center gap-1 text-sm">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
            Общая для пространства
          </label>
          <Button type="submit" size="sm" disabled={create.isPending}>
            Добавить метку
          </Button>
        </form>
      )}
    </Card>
  )
}

export function TeamSettingsPage() {
  const workspace = useCurrentWorkspace()
  const { key } = useParams({ strict: false })
  const team = useTeamByKey(workspace?.id, key)
  const writable = canWrite(useSession())
  if (!workspace || !team) return null
  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 p-4 sm:p-6">
      <h1 className="font-display text-2xl font-semibold tracking-tight">
        {team.name} <span className="text-fg-muted font-mono text-lg">{team.key}</span>
      </h1>
      <States team={team} writable={writable} />
      <Labels team={team} workspaceId={workspace.id} writable={writable} />
      <Card title="Участники команды" hint="Лид управляет статусами, метками и составом команды.">
        <MembersPanel level="team" id={team.id} workspaceId={workspace.id} />
      </Card>
    </div>
  )
}
