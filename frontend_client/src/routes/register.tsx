import { Link, createFileRoute } from '@tanstack/react-router'

import { AuthLayout } from '@/features/auth/components/AuthLayout'
import { RegisterForm } from '@/features/auth/components/RegisterForm'

export const Route = createFileRoute('/register')({
  component: RegisterPage,
})

function RegisterPage() {
  return (
    <AuthLayout
      title="Регистрация"
      description="Первый зарегистрированный становится администратором инстанса"
      footer={
        <>
          Уже есть учётная запись?{' '}
          <Link to="/login" className="text-accent underline underline-offset-4">
            Войти
          </Link>
        </>
      }
    >
      <RegisterForm />
    </AuthLayout>
  )
}
