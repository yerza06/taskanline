import { createFileRoute } from '@tanstack/react-router'

import { OnboardingPage } from '@/features/workspaces/components/OnboardingPage'

export const Route = createFileRoute('/_authed/onboarding')({
  component: OnboardingPage,
})
