import { createFileRoute } from '@tanstack/react-router'

import { WorkspaceMembersPage } from '@/features/members/components/WorkspaceMembersPage'

export const Route = createFileRoute('/_authed/w/$workspace/members')({
  component: WorkspaceMembersPage,
})
