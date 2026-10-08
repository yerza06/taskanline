import { createFileRoute } from '@tanstack/react-router'

import { WorkspacePage } from '@/features/workspaces/WorkspacePage'

export const Route = createFileRoute('/workspaces/$workspaceId')({ component: Page })

function Page() {
  const { workspaceId } = Route.useParams()
  return <WorkspacePage key={workspaceId} workspaceId={workspaceId} />
}
