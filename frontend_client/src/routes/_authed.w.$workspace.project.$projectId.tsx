import { createFileRoute } from '@tanstack/react-router'

import { ProjectTasksPage } from '@/features/tasks/components/pages'
import { validateTaskSearch } from '@/features/tasks/model/search'

export const Route = createFileRoute('/_authed/w/$workspace/project/$projectId')({
  validateSearch: validateTaskSearch,
  component: ProjectTasksPage,
})
