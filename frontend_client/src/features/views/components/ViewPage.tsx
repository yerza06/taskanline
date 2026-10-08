import { useNavigate, useParams } from '@tanstack/react-router'
import { Trash2 } from 'lucide-react'
import { useState } from 'react'

import { TaskExplorer } from '@/features/tasks/components/TaskExplorer'
import type { TaskSearch } from '@/features/tasks/model/search'
import { useDeleteView, useUpdateView, useView } from '@/features/views/api/views'
import { completeFilters } from '@/features/views/model/filters'
import { useCurrentWorkspace } from '@/features/workspaces/api/workspaces'
import { humanMessage } from '@/shared/api/messages'
import type { Filters } from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'

const SCOPE_TEXT = { user: 'Личный view', team: 'View команды', workspace: 'Общий view' } as const

/**
 * Открытый view. Его определение — значения по умолчанию среза; правки живут в
 * памяти страницы, пока их не сохранят кнопкой (если есть право менять view).
 */
export function ViewPage() {
  const workspace = useCurrentWorkspace()
  const { viewId = '' } = useParams({ strict: false })
  const view = useView(viewId)
  const update = useUpdateView(workspace?.id ?? '', viewId)
  const remove = useDeleteView(workspace?.id ?? '')
  const navigate = useNavigate()
  const [search, setSearch] = useState<TaskSearch>({})
  const [deleting, setDeleting] = useState(false)

  if (!workspace) return null
  if (view.isError) return <Alert className="m-4">{humanMessage(view.error)}</Alert>
  if (!view.data) return null
  const data = view.data

  // Командный view ограничен своей командой, даже если в фильтрах команды нет.
  const scope: Filters = data.team_id ? { team_id: { op: 'in', value: [data.team_id] } } : {}
  const changed = Object.values(search).some((value) => value !== undefined)

  return (
    <>
      <TaskExplorer
        key={data.id}
        workspace={workspace}
        title={data.name}
        subtitle={data.description ?? SCOPE_TEXT[data.scope]}
        scope={scope}
        search={search}
        defaults={{
          layout: data.layout,
          group: data.group_by ?? 'none',
          sort: data.sort_by,
          dir: data.sort_direction,
          filters: data.filters as Filters,
        }}
        onSearch={setSearch}
        allowSave={false}
        actions={
          data.can_edit && (
            <div className="flex gap-2">
              {changed && (
                <Button
                  size="sm"
                  disabled={update.isPending}
                  onClick={() => {
                    const filters = search.filters ?? (data.filters as Filters)
                    const layout = search.layout ?? data.layout
                    const group = search.group ?? data.group_by ?? 'none'
                    update.mutate(
                      {
                        filters: completeFilters(filters),
                        layout,
                        group_by: group === 'none' ? (layout === 'board' ? 'state' : null) : group,
                        sort_by: search.sort ?? data.sort_by,
                        sort_direction: search.dir ?? data.sort_direction,
                      },
                      { onSuccess: () => setSearch({}) },
                    )
                  }}
                >
                  Сохранить изменения
                </Button>
              )}
              <Button variant="ghost" size="sm" aria-label="Удалить view" onClick={() => setDeleting(true)}>
                <Trash2 aria-hidden="true" className="size-4" />
              </Button>
            </div>
          )
        }
      />
      <Dialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Удалить «${data.name}»?`}
        description="Задачи останутся на месте — пропадёт только сохранённый срез."
      >
        {remove.error && <Alert className="mb-3">{humanMessage(remove.error)}</Alert>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDeleting(false)}>
            Отмена
          </Button>
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(data.id, {
                onSuccess: () => void navigate({ to: '/w/$workspace', params: { workspace: workspace.slug } }),
              })
            }
          >
            Удалить
          </Button>
        </div>
      </Dialog>
    </>
  )
}
