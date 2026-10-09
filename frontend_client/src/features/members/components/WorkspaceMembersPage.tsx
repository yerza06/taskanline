import { MembersPanel } from '@/features/members/components/MembersPanel'
import { useCurrentWorkspace } from '@/features/workspaces/api/workspaces'

export function WorkspaceMembersPage() {
  const workspace = useCurrentWorkspace()
  if (!workspace) return null
  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Участники</h1>
        <p className="text-fg-muted mt-1 text-sm">
          Участники пространства видят открытые команды. Гость видит только то, куда его
          пригласили отдельно: команду или проект.
        </p>
      </div>
      <MembersPanel level="workspace" id={workspace.id} workspaceId={workspace.id} />
    </div>
  )
}
