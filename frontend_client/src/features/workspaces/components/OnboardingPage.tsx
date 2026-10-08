import { useNavigate } from '@tanstack/react-router'

import { CreateWorkspaceForm } from '@/features/workspaces/components/CreateWorkspaceForm'

/** Первый вход без пространств: создать своё или дождаться приглашения. */
export function OnboardingPage() {
  const navigate = useNavigate()

  return (
    <div className="mx-auto w-full max-w-md space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Новое пространство</h1>
        <p className="text-fg-muted mt-1 text-sm">
          Пространство объединяет команды, проекты и задачи. Если вас пригласили в чужое —
          откройте ссылку из письма.
        </p>
      </div>
      <section className="border-border bg-surface rounded-lg border p-4 sm:p-6">
        <CreateWorkspaceForm
          onCreated={(space) =>
            void navigate({ to: '/w/$workspace', params: { workspace: space.slug } })
          }
        />
      </section>
    </div>
  )
}
