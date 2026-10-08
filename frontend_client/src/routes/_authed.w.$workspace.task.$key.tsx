import { createFileRoute } from '@tanstack/react-router'

import { TaskPage } from '@/features/tasks/components/TaskPage'

export const Route = createFileRoute('/_authed/w/$workspace/task/$key')({
  component: TaskPage,
})
