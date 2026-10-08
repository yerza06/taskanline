import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Link, useNavigate } from '@tanstack/react-router'
import {
  Bell,
  Check,
  ChevronsUpDown,
  CircleUser,
  Columns3,
  Eye,
  FolderKanban,
  Plus,
  Settings,
  Users,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { useUi } from '@/app/ui-store'
import { canWrite, useSession } from '@/features/auth/api/session'
import { useNotifications } from '@/features/notifications/api/notifications'
import { useAllProjects } from '@/features/projects/api/projects'
import { CreateProjectDialog } from '@/features/projects/components/CreateProjectDialog'
import { useTeams } from '@/features/teams/api/teams'
import { CreateTeamDialog } from '@/features/teams/components/CreateTeamDialog'
import { useViews } from '@/features/views/api/views'
import { useWorkspaceRole, useWorkspaces } from '@/features/workspaces/api/workspaces'
import type { TeamRead, ViewRead, WorkspaceRead } from '@/shared/api/types'
import { cn } from '@/shared/lib/cn'

const LINK =
  'flex min-h-8 items-center gap-2 rounded-md px-2 py-1 text-sm text-fg-muted transition ' +
  'hover:bg-surface-hover hover:text-fg focus-visible:outline-2 focus-visible:outline-accent'
// Активный пункт отличается весом и подложкой, а не цветом: палитра чёрно-белая.
const ACTIVE = { className: 'bg-surface-hover font-semibold text-fg' }

const ITEM =
  'flex w-full cursor-default items-center gap-2 rounded px-2 py-1.5 text-sm outline-none data-highlighted:bg-surface-hover'

const SCOPE_TITLES: Record<ViewRead['scope'], string> = {
  user: 'Мои',
  team: 'Командные',
  workspace: 'Общие',
}

function Section({
  title,
  action,
  children,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="space-y-0.5">
      <div className="flex items-center justify-between px-2 pt-4 pb-1">
        <h2 className="text-fg-muted text-xs tracking-wide uppercase">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function AddButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="text-fg-muted hover:text-fg hover:bg-surface-hover focus-visible:outline-accent rounded p-0.5 focus-visible:outline-2"
    >
      <Plus aria-hidden="true" className="size-4" />
    </button>
  )
}

function WorkspaceSwitcher({ current }: { current: WorkspaceRead }) {
  const spaces = useWorkspaces().data ?? []
  const navigate = useNavigate()

  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger className="hover:bg-surface-hover focus-visible:outline-accent flex w-full items-center gap-2 rounded-md px-2 py-2 text-left focus-visible:outline-2">
        <span className="bg-accent text-accent-fg grid size-6 shrink-0 place-items-center rounded text-xs font-semibold">
          {current.name.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold">{current.name}</span>
        <ChevronsUpDown aria-hidden="true" className="text-fg-muted size-4 shrink-0" />
        <span className="sr-only">Сменить пространство</span>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={4}
          className="border-border bg-surface z-50 min-w-56 rounded-md border p-1 shadow-lg"
        >
          {spaces.map((space) => (
            <DropdownMenu.Item
              key={space.id}
              className={ITEM}
              onSelect={() =>
                void navigate({ to: '/w/$workspace', params: { workspace: space.slug } })
              }
            >
              <span className="min-w-0 flex-1 truncate">{space.name}</span>
              {space.id === current.id && <Check aria-hidden="true" className="size-4" />}
            </DropdownMenu.Item>
          ))}
          <DropdownMenu.Separator className="bg-border my-1 h-px" />
          <DropdownMenu.Item className={ITEM} onSelect={() => void navigate({ to: '/onboarding' })}>
            <Plus aria-hidden="true" className="size-4" />
            Новое пространство
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

function TeamItem({
  workspace,
  team,
  projects,
  onAddProject,
  writable,
}: {
  workspace: string
  team: TeamRead
  projects: { id: string; name: string; team_id: string }[]
  onAddProject: () => void
  writable: boolean
}) {
  const params = { workspace, key: team.key }
  return (
    <li>
      <div className="group flex items-center">
        <Link
          to="/w/$workspace/team/$key"
          params={params}
          search={{}}
          activeOptions={{ exact: true, includeSearch: false }}
          activeProps={ACTIVE}
          className={cn(LINK, 'min-w-0 flex-1')}
        >
          <span className="border-border grid h-5 min-w-8 place-items-center rounded border px-1 text-[10px] font-semibold">
            {team.key}
          </span>
          <span className="truncate">{team.name}</span>
        </Link>
        <Link
          to="/w/$workspace/team/$key"
          params={params}
          search={{ layout: 'board' }}
          aria-label={`Доска ${team.key}`}
          title="Доска"
          className="text-fg-muted hover:text-fg hover:bg-surface-hover rounded p-1"
        >
          <Columns3 aria-hidden="true" className="size-4" />
        </Link>
        <Link
          to="/w/$workspace/team/$key/settings"
          params={params}
          aria-label={`Настройки ${team.key}`}
          title="Настройки команды"
          className="text-fg-muted hover:text-fg hover:bg-surface-hover rounded p-1"
        >
          <Settings aria-hidden="true" className="size-4" />
        </Link>
      </div>
      <ul className="border-border ml-4 border-l pl-1">
        {projects.map((project) => (
          <li key={project.id}>
            <Link
              to="/w/$workspace/project/$projectId"
              params={{ workspace, projectId: project.id }}
              activeProps={ACTIVE}
              className={LINK}
            >
              <FolderKanban aria-hidden="true" className="size-4 shrink-0" />
              <span className="truncate">{project.name}</span>
            </Link>
          </li>
        ))}
        {writable && (
          <li>
            <button type="button" onClick={onAddProject} className={cn(LINK, 'w-full')}>
              <Plus aria-hidden="true" className="size-4" />
              Проект
            </button>
          </li>
        )}
      </ul>
    </li>
  )
}

/**
 * Боковое меню пространства: свои задачи, входящие, команды с проектами, views.
 *
 * На узком экране оно выезжает поверх контента (`sidebarOpen` в общем
 * состоянии) и закрывается переходом по любой ссылке.
 */
export function Sidebar({ workspace }: { workspace: WorkspaceRead }) {
  const session = useSession()
  const writable = canWrite(session)
  const role = useWorkspaceRole(workspace.id)
  const teams = useTeams(workspace.id).data ?? []
  const projects = useAllProjects(teams)
  const views = useViews(workspace.id).data ?? []
  const unread = useNotifications({ unread: true }).data?.items.length ?? 0
  const navigate = useNavigate()
  const setSidebarOpen = useUi((state) => state.setSidebarOpen)
  const [creatingTeam, setCreatingTeam] = useState(false)
  const [projectTeam, setProjectTeam] = useState<TeamRead | null>(null)
  const slug = workspace.slug

  const canCreateTeam = writable && (role === 'owner' || role === 'admin' || role === 'member')

  return (
    <nav
      aria-label="Навигация по пространству"
      className="flex h-full flex-col overflow-y-auto p-2"
      onClick={(event) => {
        if ((event.target as HTMLElement).closest('a')) setSidebarOpen(false)
      }}
    >
      <WorkspaceSwitcher current={workspace} />

      <div className="mt-2 space-y-0.5">
        <Link
          to="/w/$workspace"
          params={{ workspace: slug }}
          activeOptions={{ exact: true }}
          activeProps={ACTIVE}
          className={LINK}
        >
          <CircleUser aria-hidden="true" className="size-4" />
          Мои задачи
        </Link>
        <Link to="/w/$workspace/inbox" params={{ workspace: slug }} activeProps={ACTIVE} className={LINK}>
          <Bell aria-hidden="true" className="size-4" />
          Входящие
          {unread > 0 && (
            <span className="bg-accent text-accent-fg ml-auto rounded-full px-1.5 text-xs font-semibold">
              {unread}
              <span className="sr-only"> непрочитанных</span>
            </span>
          )}
        </Link>
        <Link to="/w/$workspace/members" params={{ workspace: slug }} activeProps={ACTIVE} className={LINK}>
          <Users aria-hidden="true" className="size-4" />
          Участники
        </Link>
      </div>

      <Section
        title="Команды"
        action={
          canCreateTeam ? <AddButton label="Новая команда" onClick={() => setCreatingTeam(true)} /> : null
        }
      >
        {teams.length === 0 ? (
          <p className="text-fg-muted px-2 text-sm">Команд пока нет.</p>
        ) : (
          <ul className="space-y-1">
            {teams.map((team) => (
              <TeamItem
                key={team.id}
                workspace={slug}
                team={team}
                projects={projects.filter((project) => project.team_id === team.id)}
                onAddProject={() => setProjectTeam(team)}
                writable={writable}
              />
            ))}
          </ul>
        )}
      </Section>

      {(['user', 'team', 'workspace'] as const).map((scope) => {
        const items = views.filter((view) => view.scope === scope)
        if (items.length === 0) return null
        return (
          <Section key={scope} title={`Views · ${SCOPE_TITLES[scope]}`}>
            <ul>
              {items.map((view) => (
                <li key={view.id}>
                  <Link
                    to="/w/$workspace/view/$viewId"
                    params={{ workspace: slug, viewId: view.id }}
                    activeProps={ACTIVE}
                    className={LINK}
                  >
                    <Eye aria-hidden="true" className="size-4 shrink-0" />
                    <span className="truncate">{view.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        )
      })}

      <CreateTeamDialog
        workspaceId={workspace.id}
        open={creatingTeam}
        onOpenChange={setCreatingTeam}
        onCreated={(team) => {
          setCreatingTeam(false)
          void navigate({ to: '/w/$workspace/team/$key', params: { workspace: slug, key: team.key }, search: {} })
        }}
      />
      {projectTeam && (
        <CreateProjectDialog
          teamId={projectTeam.id}
          teamKey={projectTeam.key}
          open
          onOpenChange={(open) => !open && setProjectTeam(null)}
          onCreated={(project) => {
            setProjectTeam(null)
            void navigate({
              to: '/w/$workspace/project/$projectId',
              params: { workspace: slug, projectId: project.id },
            })
          }}
        />
      )}
    </nav>
  )
}
