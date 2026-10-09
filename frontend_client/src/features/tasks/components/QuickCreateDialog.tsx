import { useNavigate, useParams } from '@tanstack/react-router'
import { useState } from 'react'

import { useUi } from '@/app/ui-store'
import { useCreateTask } from '@/features/tasks/api/tasks'
import { PRIORITY_LABELS } from '@/features/tasks/model/labels'
import { useProject } from '@/features/projects/api/projects'
import { useStates, useTeams } from '@/features/teams/api/teams'
import { humanMessage } from '@/shared/api/messages'
import type { WorkspaceRead } from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'
import { Select } from '@/shared/ui/Select'
import { Textarea } from '@/shared/ui/Textarea'

/**
 * Быстрое создание задачи с клавиатуры: `c` — окно, Enter — создать.
 *
 * Команда и проект берутся из открытого экрана: на странице проекта задача сразу
 * попадает в него. Остальное — необязательно и правится уже в карточке.
 */
export function QuickCreateDialog({ workspace }: { workspace: WorkspaceRead }) {
  const open = useUi((state) => state.quickCreateOpen)
  const setOpen = useUi((state) => state.setQuickCreateOpen)
  const params = useParams({ strict: false })
  const teams = useTeams(workspace.id).data ?? []
  const project = useProject(params.projectId).data
  const contextTeam =
    teams.find((team) => team.key === params.key?.toUpperCase()) ??
    teams.find((team) => team.id === project?.team_id)
  const [teamId, setTeamId] = useState<string>('')
  const chosenTeam = teams.find((team) => team.id === teamId) ?? contextTeam ?? teams[0]
  const states = useStates(chosenTeam?.id).data ?? []
  const create = useCreateTask()
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [stateId, setStateId] = useState('')
  const [priority, setPriority] = useState(0)
  const [titleError, setTitleError] = useState<string | null>(null)

  function close() {
    setOpen(false)
    setTitle('')
    setDescription('')
    setStateId('')
    setPriority(0)
    setTeamId('')
    setTitleError(null)
    create.reset()
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? setOpen(true) : close())}
      title="Новая задача"
      description={chosenTeam ? `Номер будет вида ${chosenTeam.key}-…` : 'Сначала создайте команду'}
    >
      {teams.length === 0 ? (
        <p className="text-fg-muted text-sm">У задачи должна быть команда — создайте её в боковом меню.</p>
      ) : (
        <form
          noValidate
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!title.trim()) {
              setTitleError('Назовите задачу')
              return
            }
            if (!chosenTeam) return
            const inProject = project && project.team_id === chosenTeam.id
            create.mutate(
              {
                title: title.trim(),
                description: description.trim() || null,
                team_id: inProject ? null : chosenTeam.id,
                project_id: inProject ? project.id : null,
                state_id: stateId || null,
                priority,
              },
              {
                onSuccess: (task) => {
                  close()
                  void navigate({
                    to: '/w/$workspace/task/$key',
                    params: { workspace: workspace.slug, key: task.key },
                  })
                },
              },
            )
          }}
        >
          {create.error && <Alert>{humanMessage(create.error)}</Alert>}
          <Field label="Название" error={titleError ?? undefined}>
            {(control) => (
              <Input {...control} value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
            )}
          </Field>
          <Field label="Описание" hint="Markdown, необязательно">
            {(control) => (
              <Textarea
                {...control}
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onKeyDown={(e) => {
                  // В многострочном поле Enter — перенос; создать — Ctrl/⌘+Enter.
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit()
                }}
              />
            )}
          </Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Команда">
              {(control) => (
                <Select
                  {...control}
                  className="w-full"
                  value={chosenTeam?.id ?? ''}
                  onChange={(e) => {
                    setTeamId(e.target.value)
                    setStateId('')
                  }}
                >
                  {teams.map((team) => (
                    <option key={team.id} value={team.id}>
                      {team.key}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Статус">
              {(control) => (
                <Select {...control} className="w-full" value={stateId} onChange={(e) => setStateId(e.target.value)}>
                  <option value="">По умолчанию</option>
                  {states.map((state) => (
                    <option key={state.id} value={state.id}>
                      {state.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Приоритет">
              {(control) => (
                <Select
                  {...control}
                  className="w-full"
                  value={priority}
                  onChange={(e) => setPriority(Number(e.target.value))}
                >
                  {[0, 1, 2, 3, 4].map((p) => (
                    <option key={p} value={p}>
                      {PRIORITY_LABELS[p]}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          {project && chosenTeam?.id === project.team_id && (
            <p className="text-fg-muted text-xs">Задача попадёт в проект «{project.name}».</p>
          )}
          <Button type="submit" disabled={create.isPending}>
            Создать задачу
          </Button>
        </form>
      )}
    </Dialog>
  )
}
