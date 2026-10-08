import { Outlet } from '@tanstack/react-router'
import { Menu, X } from 'lucide-react'

import { HelpDialog } from '@/app/HelpDialog'
import { useHotkeys } from '@/app/hotkeys'
import { useUi } from '@/app/ui-store'
import { QuickCreateDialog } from '@/features/tasks/components/QuickCreateDialog'
import { useCurrentWorkspace } from '@/features/workspaces/api/workspaces'
import { Sidebar } from '@/features/workspaces/components/Sidebar'
import type { WorkspaceRead } from '@/shared/api/types'
import { cn } from '@/shared/lib/cn'

function Shell({ workspace }: { workspace: WorkspaceRead }) {
  const open = useUi((state) => state.sidebarOpen)
  const setOpen = useUi((state) => state.setSidebarOpen)
  useHotkeys(workspace)

  return (
    <div className="relative flex h-full min-h-0">
      {/* На широком экране меню стоит слева всегда; на узком выезжает поверх. */}
      <aside
        className={cn(
          'border-border bg-surface z-30 w-64 shrink-0 border-r',
          'max-md:fixed max-md:inset-y-14 max-md:left-0 max-md:shadow-xl max-md:transition-transform',
          open ? 'max-md:translate-x-0' : 'max-md:-translate-x-full',
        )}
      >
        <Sidebar workspace={workspace} />
      </aside>
      {open && (
        <button
          type="button"
          aria-label="Закрыть меню"
          className="fixed inset-0 top-14 z-20 bg-black/40 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-border flex items-center gap-2 border-b px-2 py-1 md:hidden">
          <button
            type="button"
            aria-label={open ? 'Закрыть меню' : 'Открыть меню'}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
            className="hover:bg-surface-hover rounded p-2"
          >
            {open ? <X aria-hidden="true" className="size-5" /> : <Menu aria-hidden="true" className="size-5" />}
          </button>
          <span className="truncate text-sm font-semibold">{workspace.name}</span>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </div>
      </div>
      <QuickCreateDialog workspace={workspace} />
      <HelpDialog />
    </div>
  )
}

export function WorkspaceLayout() {
  const workspace = useCurrentWorkspace()
  if (!workspace) return null
  return <Shell key={workspace.id} workspace={workspace} />
}
