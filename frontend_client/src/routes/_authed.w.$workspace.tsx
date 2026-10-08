import { createFileRoute, notFound } from '@tanstack/react-router'

import { workspacesQueryOptions } from '@/features/workspaces/api/workspaces'
import { WorkspaceLayout } from '@/features/workspaces/components/WorkspaceLayout'

/**
 * Ветка пространства. Чужой или несуществующий slug — «страница не найдена»,
 * а не пустое меню: существование чужого пространства не раскрывается (как 404 API).
 */
export const Route = createFileRoute('/_authed/w/$workspace')({
  beforeLoad: async ({ context, params }) => {
    const { items } = await context.queryClient.ensureQueryData(workspacesQueryOptions())
    if (!items.some((space) => space.slug === params.workspace)) {
      throw notFound()
    }
  },
  component: WorkspaceLayout,
})
