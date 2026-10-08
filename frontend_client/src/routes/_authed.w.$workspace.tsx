import { createFileRoute, notFound } from '@tanstack/react-router'

import { workspacesQueryOptions } from '@/features/workspaces/api/workspaces'
import { WorkspaceLayout } from '@/features/workspaces/components/WorkspaceLayout'

/**
 * Ветка пространства. Чужой или несуществующий slug — «страница не найдена»,
 * а не пустое меню: существование чужого пространства не раскрывается (как 404 API).
 */
export const Route = createFileRoute('/_authed/w/$workspace')({
  beforeLoad: async ({ context, params }) => {
    const known = (items: { slug: string }[]) => items.some((s) => s.slug === params.workspace)
    const cached = await context.queryClient.ensureQueryData(workspacesQueryOptions())
    if (known(cached.items)) return
    // Незнакомый slug — возможно, кэш отстал (только что приняли приглашение).
    // Переспросить сервер, и лишь потом сказать «не найдено».
    const fresh = await context.queryClient.fetchQuery({ ...workspacesQueryOptions(), staleTime: 0 })
    if (!known(fresh.items)) {
      throw notFound()
    }
  },
  component: WorkspaceLayout,
})
