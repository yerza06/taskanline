import { useState } from 'react'

import { useCreateView } from '@/features/views/api/views'
import { humanMessage } from '@/shared/api/messages'
import type {
  Filters,
  SortDirection,
  TeamRead,
  ViewGroupBy,
  ViewLayout,
  ViewRead,
  ViewScope,
  ViewSortBy,
} from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'
import { Select } from '@/shared/ui/Select'

export interface ViewDraft {
  filters: Filters
  group_by: ViewGroupBy | null
  sort_by: ViewSortBy
  sort_direction: SortDirection
  layout: ViewLayout
}

const SCOPE_LABELS: Record<ViewScope, string> = {
  user: 'Только мне',
  team: 'Команде',
  workspace: 'Всему пространству',
}

/** Сохранить текущий срез: фильтры, группировку, сортировку и вид — под именем. */
export function SaveViewDialog({
  workspaceId,
  teams,
  defaultTeamId,
  draft,
  open,
  onOpenChange,
  onSaved,
}: {
  workspaceId: string
  teams: TeamRead[]
  defaultTeamId?: string
  draft: ViewDraft
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: (view: ViewRead) => void
}) {
  const create = useCreateView(workspaceId)
  const [name, setName] = useState('')
  const [scope, setScope] = useState<ViewScope>('user')
  const [teamId, setTeamId] = useState(defaultTeamId ?? teams[0]?.id ?? '')
  const [nameError, setNameError] = useState<string | null>(null)

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Сохранить view"
      description="Срез появится в боковом меню и откроется за один щелчок."
    >
      <form
        noValidate
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (!name.trim()) {
            setNameError('Назовите view')
            return
          }
          setNameError(null)
          // Фильтр команды для командного view лишний: он ограничен своей командой сам.
          const filters = { ...draft.filters }
          if (scope === 'team') delete filters.team_id
          create.mutate(
            {
              ...draft,
              filters,
              name: name.trim(),
              scope,
              team_id: scope === 'team' ? teamId : null,
            },
            { onSuccess: onSaved },
          )
        }}
      >
        {create.error && <Alert>{humanMessage(create.error)}</Alert>}
        <Field label="Название" error={nameError ?? undefined}>
          {(control) => (
            <Input {...control} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          )}
        </Field>
        <Field label="Кому виден">
          {(control) => (
            <Select
              {...control}
              className="w-full"
              value={scope}
              onChange={(e) => setScope(e.target.value as ViewScope)}
            >
              {(Object.keys(SCOPE_LABELS) as ViewScope[]).map((value) => (
                <option key={value} value={value}>
                  {SCOPE_LABELS[value]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {scope === 'team' && (
          <Field label="Команда">
            {(control) => (
              <Select
                {...control}
                className="w-full"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
              >
                {teams.map((team) => (
                  <option key={team.id} value={team.id}>
                    {team.key} · {team.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        <Button type="submit" disabled={create.isPending}>
          Сохранить
        </Button>
      </form>
    </Dialog>
  )
}
