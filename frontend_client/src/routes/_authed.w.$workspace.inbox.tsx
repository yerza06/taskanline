import { createFileRoute } from '@tanstack/react-router'

import { InboxPage } from '@/features/notifications/components/InboxPage'

export const Route = createFileRoute('/_authed/w/$workspace/inbox')({
  component: InboxPage,
})
