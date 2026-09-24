import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { SESSION_KEY } from '@/features/auth/api/session'
import { loginSchema, type LoginValues } from '@/features/auth/model/schemas'
import { applyServerError } from '@/features/auth/model/server-errors'
import { apiFetch, markSessionActive } from '@/shared/api/client'
import type { SessionResponse } from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'

export function LoginForm({ redirectTo }: { redirectTo?: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  })

  const login = useMutation({
    mutationFn: (values: LoginValues) =>
      apiFetch<SessionResponse>('/auth/login', { method: 'POST', json: values }),
    onSuccess: async () => {
      markSessionActive()
      // Вход отдаёт UserRead — без auth_method и scopes. Класть его в кэш
      // сессии нельзя: защита маршрута должна спросить /me заново.
      queryClient.removeQueries({ queryKey: SESSION_KEY })
      // Путь пришёл из адресной строки и уже проверен на «внутренний»;
      // статически сопоставить его с деревом маршрутов нельзя.
      await navigate({ to: (redirectTo ?? '/profile') as '/profile' })
    },
    onError: (error) => {
      setFormError(applyServerError(error, setError, ['email', 'password']))
    },
  })

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) =>
        void handleSubmit((values) => {
          setFormError(null)
          login.mutate(values)
        })(event)
      }
    >
      {formError && <Alert>{formError}</Alert>}

      <Field label="Email" error={errors.email?.message}>
        {(control) => (
          <Input {...control} {...register('email')} type="email" autoComplete="email" autoFocus />
        )}
      </Field>

      <Field label="Пароль" error={errors.password?.message}>
        {(control) => (
          <Input
            {...control}
            {...register('password')}
            type="password"
            autoComplete="current-password"
          />
        )}
      </Field>

      <Button type="submit" className="w-full" disabled={login.isPending}>
        {login.isPending ? 'Входим…' : 'Войти'}
      </Button>
    </form>
  )
}
