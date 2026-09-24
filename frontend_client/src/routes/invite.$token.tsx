import { createFileRoute } from '@tanstack/react-router'

import { InvitePage } from '@/features/invitations/components/InvitePage'

/** Вне `_authed`: по ссылке из письма приходит и тот, у кого учётной записи ещё нет. */
export const Route = createFileRoute('/invite/$token')({
  component: InviteRoute,
})

function InviteRoute() {
  const { token } = Route.useParams()
  return <InvitePage token={token} />
}
