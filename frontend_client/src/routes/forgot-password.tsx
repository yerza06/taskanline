import { Link, createFileRoute } from '@tanstack/react-router'

import { AuthLayout } from '@/features/auth/components/AuthLayout'
import { ForgotPasswordForm } from '@/features/auth/components/PasswordResetForms'

export const Route = createFileRoute('/forgot-password')({
  component: ForgotPasswordPage,
})

function ForgotPasswordPage() {
  return (
    <AuthLayout
      title="Смена пароля"
      description="Пришлём ссылку, по которой можно задать новый пароль"
      footer={
        <Link to="/login" className="text-accent underline underline-offset-4">
          Вернуться ко входу
        </Link>
      }
    >
      <ForgotPasswordForm />
    </AuthLayout>
  )
}
