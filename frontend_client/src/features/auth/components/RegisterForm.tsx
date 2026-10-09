import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { SESSION_KEY } from '@/features/auth/api/session'
import { PasswordInput } from '@/features/auth/components/PasswordInput'
import { registerSchema, type RegisterValues } from '@/features/auth/model/schemas'
import { applyServerError } from '@/features/auth/model/server-errors'
import { apiFetch, markSessionActive } from '@/shared/api/client'
import type { SessionResponse } from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'

export function RegisterForm() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: '', full_name: '', password: '' },
  })

  const signUp = useMutation({
    mutationFn: (values: RegisterValues) =>
      apiFetch<SessionResponse>('/auth/register', { method: 'POST', json: values }),
    onSuccess: async () => {
      // Регистрация сразу открывает сессию — cookie уже стоят, входить незачем.
      markSessionActive()
      queryClient.removeQueries({ queryKey: SESSION_KEY })
      // Корень сам решит: пространства ещё нет — на создание первого.
      await navigate({ to: '/' })
    },
    onError: (error) => {
      setFormError(applyServerError(error, setError, ['email', 'full_name', 'password']))
    },
  })

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) =>
        void handleSubmit((values) => {
          setFormError(null)
          signUp.mutate(values)
        })(event)
      }
    >
      {formError && <Alert>{formError}</Alert>}

      <Field label="Email" error={errors.email?.message}>
        {(control) => (
          <Input {...control} {...register('email')} type="email" autoComplete="email" autoFocus />
        )}
      </Field>

      <Field label="Имя" error={errors.full_name?.message}>
        {(control) => <Input {...control} {...register('full_name')} autoComplete="name" />}
      </Field>

      <Field
        label="Пароль"
        error={errors.password?.message}
        hint="Не короче восьми символов"
      >
        {(control) => (
          <PasswordInput {...control} {...register('password')} autoComplete="new-password" />
        )}
      </Field>

      <Button type="submit" className="w-full" disabled={signUp.isPending}>
        {signUp.isPending ? 'Создаём…' : 'Зарегистрироваться'}
      </Button>
    </form>
  )
}
