import { createFileRoute } from '@tanstack/react-router'

import { TeamSettingsPage } from '@/features/teams/components/TeamSettingsPage'

export const Route = createFileRoute('/_authed/w/$workspace/team/$key/settings')({
  component: TeamSettingsPage,
})
