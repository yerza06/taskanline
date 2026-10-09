import { Link, createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'

import { AuthLayout } from '@/features/auth/components/AuthLayout'
import { LoginForm } from '@/features/auth/components/LoginForm'

/**
 * Куда вернуть человека после входа.
 *
 * Только внутренний путь: подставленный в параметр чужой адрес превратил бы
 * форму входа в открытый редирект на фишинговую копию.
 */
function internalPath(value: string | undefined): string | undefined {
  if (!value?.startsWith('/') || value.startsWith('//')) {
    return undefined
  }
  return value
}

const searchSchema = z.object({
  redirect: z.string().optional().transform(internalPath),
})

export const Route = createFileRoute('/login')({
  validateSearch: searchSchema,
  component: LoginPage,
})

function LoginPage() {
  const { redirect } = Route.useSearch()

  return (
    <AuthLayout
      title="Вход"
      description="Войдите, чтобы вернуться к задачам"
      footer={
        <>
          Нет учётной записи?{' '}
          <Link to="/register" className="text-accent underline underline-offset-4">
            Зарегистрироваться
          </Link>
        </>
      }
    >
      <LoginForm redirectTo={redirect} />
      <p className="mt-4 text-center text-sm">
        <Link to="/forgot-password" className="text-fg-muted underline underline-offset-4">
          Забыли пароль?
        </Link>
      </p>
    </AuthLayout>
  )
}
