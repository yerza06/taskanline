import { createFileRoute } from '@tanstack/react-router'

import { UserPage } from '@/features/users/UserPage'

export const Route = createFileRoute('/users/$userId')({ component: Page })

function Page() {
  const { userId } = Route.useParams()
  return <UserPage key={userId} userId={userId} />
}
