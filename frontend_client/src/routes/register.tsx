import { Link, createFileRoute } from '@tanstack/react-router'

import { useInstance } from '@/features/auth/api/instance'
import { AuthLayout } from '@/features/auth/components/AuthLayout'
import { RegisterForm } from '@/features/auth/components/RegisterForm'

export const Route = createFileRoute('/register')({
  component: RegisterPage,
})

function RegisterPage() {
  const instance = useInstance()
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
      {instance?.registration_mode === 'invite_only' && (
        <p role="note" className="border-border mb-4 rounded-md border border-l-4 px-3 py-2 text-sm">
          На этом сервере регистрация только по приглашению. Если вас пригласили — откройте
          ссылку из письма.
        </p>
      )}
      {instance?.registration_mode === 'domain_allowlist' && (
        <p role="note" className="border-border mb-4 rounded-md border border-l-4 px-3 py-2 text-sm">
          Самостоятельно зарегистрироваться можно только с рабочего адреса организации.
        </p>
      )}
      <RegisterForm />
    </AuthLayout>
  )
}
