import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { SESSION_KEY } from '@/features/auth/api/session'
import { PasswordInput } from '@/features/auth/components/PasswordInput'
import { forgotSchema, resetSchema } from '@/features/auth/model/schemas'
import { apiFetch, markSessionActive } from '@/shared/api/client'
import { humanMessage } from '@/shared/api/messages'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'

/**
 * «Забыл пароль». Ответ сервера одинаков, есть такой адрес или нет, — и экран
 * говорит одно и то же: по нему нельзя узнать, кто зарегистрирован.
 */
export function ForgotPasswordForm() {
  const [sent, setSent] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<{ email: string }>({ resolver: zodResolver(forgotSchema), defaultValues: { email: '' } })
  const request = useMutation({
    mutationFn: (values: { email: string }) =>
      apiFetch<void>('/auth/forgot-password', { method: 'POST', json: values }),
    onSuccess: (_, values) => setSent(values.email),
  })

  if (sent) {
    return (
      <p role="status" className="text-sm">
        Если адрес {sent} зарегистрирован, на него ушло письмо со ссылкой. Она действует час.
      </p>
    )
  }
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) => void handleSubmit((values) => request.mutate(values))(event)}
    >
      {request.error && <Alert>{humanMessage(request.error)}</Alert>}
      <Field label="Email" error={errors.email?.message}>
        {(control) => <Input {...control} {...register('email')} type="email" autoComplete="email" />}
      </Field>
      <Button type="submit" className="w-full" disabled={request.isPending}>
        Прислать ссылку
      </Button>
    </form>
  )
}

/** Новый пароль по ссылке из письма: прежние сессии гаснут, открывается новая. */
export function ResetPasswordForm({ token }: { token: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<{ password: string }>({
    resolver: zodResolver(resetSchema),
    defaultValues: { password: '' },
  })
  const reset = useMutation({
    mutationFn: (values: { password: string }) =>
      apiFetch('/auth/reset-password', { method: 'POST', json: { token, ...values } }),
    onSuccess: async () => {
      markSessionActive()
      queryClient.removeQueries({ queryKey: SESSION_KEY })
      await navigate({ to: '/' })
    },
  })

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) => void handleSubmit((values) => reset.mutate(values))(event)}
    >
      {reset.error && <Alert>{humanMessage(reset.error)}</Alert>}
      <Field label="Новый пароль" error={errors.password?.message} hint="Не короче восьми символов">
        {(control) => (
          <PasswordInput {...control} {...register('password')} autoComplete="new-password" />
        )}
      </Field>
      <Button type="submit" className="w-full" disabled={reset.isPending}>
        Сменить пароль и войти
      </Button>
    </form>
  )
}
