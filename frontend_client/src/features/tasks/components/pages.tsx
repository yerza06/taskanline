import { Link, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { Plus, Settings, Users } from 'lucide-react'
import { useState } from 'react'

import { useUi } from '@/app/ui-store'
import { canWrite, useSession } from '@/features/auth/api/session'
import { MembersPanel } from '@/features/members/components/MembersPanel'
import { useProject } from '@/features/projects/api/projects'
import { TaskExplorer, type ExplorerDefaults } from '@/features/tasks/components/TaskExplorer'
import { formatDate } from '@/features/tasks/model/groups'
import type { TaskSearch } from '@/features/tasks/model/search'
import { useTeamByKey, useTeams } from '@/features/teams/api/teams'
import { useCurrentWorkspace } from '@/features/workspaces/api/workspaces'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'

/** Адресная строка — источник состояния среза; изменение — новый адрес. */
function useTaskSearch(): [TaskSearch, (search: TaskSearch) => void] {
  const search: TaskSearch = useSearch({ strict: false })
  const navigate = useNavigate()
  return [
    search,
    (next) =>
      void navigate({
        to: '.',
        // Пустые значения не тащим в адрес: ссылка должна оставаться короткой.
        search: Object.fromEntries(Object.entries(next).filter(([, v]) => v !== undefined)),
        replace: true,
      }),
  ]
}

function NewTaskButton() {
  const writable = canWrite(useSession())
  const open = useUi((state) => state.setQuickCreateOpen)
  if (!writable) return null
  return (
    <Button size="sm" onClick={() => open(true)} aria-keyshortcuts="c">
      <Plus aria-hidden="true" className="size-4" />
      Задача
    </Button>
  )
}

function NotFound({ what }: { what: string }) {
  return <p className="text-fg-muted p-8 text-center text-sm">{what} не найден(а) или недоступен(на).</p>
}

const LIST_DEFAULTS: ExplorerDefaults = {
  layout: 'list',
  group: 'state',
  sort: 'manual',
  dir: 'asc',
  filters: {},
}

/** «Мои задачи»: открытые задачи, назначенные на меня, во всех командах. */
export function MyTasksPage() {
  const workspace = useCurrentWorkspace()
  const [search, setSearch] = useTaskSearch()
  if (!workspace) return null
  return (
    <TaskExplorer
      workspace={workspace}
      title="Мои задачи"
      subtitle="Назначенные на вас и ещё не закрытые"
      scope={{ assignee_id: { op: 'in', value: ['@me'] } }}
      search={search}
      defaults={{
        ...LIST_DEFAULTS,
        group: 'priority',
        filters: { state_type: { op: 'nin', value: ['completed', 'canceled'] } },
      }}
      onSearch={setSearch}
      actions={<NewTaskButton />}
    />
  )
}

export function TeamTasksPage() {
  const workspace = useCurrentWorkspace()
  const { key } = useParams({ strict: false })
  const team = useTeamByKey(workspace?.id, key)
  const teams = useTeams(workspace?.id)
  const [search, setSearch] = useTaskSearch()
  if (!workspace) return null
  if (!team) return teams.isSuccess ? <NotFound what="Команда" /> : null
  return (
    <TaskExplorer
      key={team.id}
      workspace={workspace}
      team={team}
      title={team.name}
      subtitle={`Задачи команды ${team.key}`}
      scope={{ team_id: { op: 'in', value: [team.id] } }}
      search={search}
      defaults={LIST_DEFAULTS}
      onSearch={setSearch}
      actions={
        <>
          <NewTaskButton />
          <Link
            to="/w/$workspace/team/$key/settings"
            params={{ workspace: workspace.slug, key: team.key }}
            className="text-fg-muted hover:text-fg hover:bg-surface-hover rounded p-1.5"
            aria-label="Настройки команды"
          >
            <Settings aria-hidden="true" className="size-4" />
          </Link>
        </>
      }
    />
  )
}

export function ProjectTasksPage() {
  const workspace = useCurrentWorkspace()
  const { projectId } = useParams({ strict: false })
  const project = useProject(projectId)
  const team = useTeams(workspace?.id).data?.find((t) => t.id === project.data?.team_id)
  const [search, setSearch] = useTaskSearch()
  const [members, setMembers] = useState(false)
  if (!workspace) return null
  if (project.isError) return <NotFound what="Проект" />
  if (!project.data) return null
  const target = project.data.target_date ? ` · цель ${formatDate(project.data.target_date)}` : ''
  return (
    <TaskExplorer
      key={project.data.id}
      workspace={workspace}
      team={team}
      title={project.data.name}
      subtitle={`Проект${team ? ` команды ${team.key}` : ''}${target}`}
      scope={{ project_id: { op: 'in', value: [project.data.id] } }}
      search={search}
      defaults={LIST_DEFAULTS}
      onSearch={setSearch}
      actions={
        <>
          <NewTaskButton />
          <Button variant="secondary" size="sm" onClick={() => setMembers(true)}>
            <Users aria-hidden="true" className="size-4" />
            Участники
          </Button>
          <Dialog
            open={members}
            onOpenChange={setMembers}
            title={`Участники «${project.data.name}»`}
            description="Приглашённый в проект видит только его задачи — ни других проектов, ни команды целиком."
          >
            <MembersPanel level="project" id={project.data.id} workspaceId={workspace.id} />
          </Dialog>
        </>
      }
    />
  )
}
