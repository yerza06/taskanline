import { createFileRoute, redirect } from '@tanstack/react-router'

import { workspacesQueryOptions } from '@/features/workspaces/api/workspaces'

/**
 * Корень ведёт в первое пространство, а человека без пространств — создать своё.
 * Сессию к этому моменту уже проверила ветка `_authed`.
 */
export const Route = createFileRoute('/_authed/')({
  beforeLoad: async ({ context }) => {
    const { items } = await context.queryClient.ensureQueryData(workspacesQueryOptions())
    const first = items[0]
    if (!first) {
      throw redirect({ to: '/onboarding' })
    }
    throw redirect({ to: '/w/$workspace', params: { workspace: first.slug } })
  },
})
