import { createFileRoute } from '@tanstack/react-router'

import { TeamTasksPage } from '@/features/tasks/components/pages'
import { validateTaskSearch } from '@/features/tasks/model/search'

export const Route = createFileRoute('/_authed/w/$workspace/team/$key/')({
  validateSearch: validateTaskSearch,
  component: TeamTasksPage,
})
