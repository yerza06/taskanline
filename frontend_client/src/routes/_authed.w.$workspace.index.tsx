import { createFileRoute } from '@tanstack/react-router'

import { MyTasksPage } from '@/features/tasks/components/pages'
import { validateTaskSearch } from '@/features/tasks/model/search'

export const Route = createFileRoute('/_authed/w/$workspace/')({
  validateSearch: validateTaskSearch,
  component: MyTasksPage,
})
