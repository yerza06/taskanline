import { createFileRoute } from '@tanstack/react-router'

import { ViewPage } from '@/features/views/components/ViewPage'

export const Route = createFileRoute('/_authed/w/$workspace/view/$viewId')({
  component: ViewPage,
})
