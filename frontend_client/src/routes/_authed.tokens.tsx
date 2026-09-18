import { createFileRoute } from '@tanstack/react-router'

import { TokensPage } from '@/features/tokens/components/TokensPage'

export const Route = createFileRoute('/_authed/tokens')({
  component: TokensPage,
})
