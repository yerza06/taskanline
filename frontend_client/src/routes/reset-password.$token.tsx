import { Link, createFileRoute } from '@tanstack/react-router'

import { AuthLayout } from '@/features/auth/components/AuthLayout'
import { ResetPasswordForm } from '@/features/auth/components/PasswordResetForms'

export const Route = createFileRoute('/reset-password/$token')({
  component: ResetPasswordPage,
})

function ResetPasswordPage() {
  const { token } = Route.useParams()
  return (
    <AuthLayout
      title="Новый пароль"
      description="После смены все прежние сессии закроются"
      footer={
        <Link to="/forgot-password" className="text-accent underline underline-offset-4">
          Запросить новую ссылку
        </Link>
      }
    >
      <ResetPasswordForm token={token} />
    </AuthLayout>
  )
}
