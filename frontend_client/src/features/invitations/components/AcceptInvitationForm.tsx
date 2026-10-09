import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import type { z } from 'zod'

import { PasswordInput } from '@/features/auth/components/PasswordInput'
import { registerSchema } from '@/features/auth/model/schemas'
import { applyServerError } from '@/features/auth/model/server-errors'
import { useAcceptInvitation } from '@/features/invitations/api/invitations'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'

// Email не спрашивается: учётная запись заводится ровно на адрес из приглашения.
const acceptSchema = registerSchema.pick({ full_name: true, password: true })
type AcceptValues = z.infer<typeof acceptSchema>

export function AcceptInvitationForm({ token, email }: { token: string; email: string }) {
  const accept = useAcceptInvitation(token)
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<AcceptValues>({
    resolver: zodResolver(acceptSchema),
    defaultValues: { full_name: '', password: '' },
  })

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) =>
        void handleSubmit((values) => {
          setFormError(null)
          accept.mutate(values, {
            onError: (error) =>
              setFormError(applyServerError(error, setError, ['full_name', 'password'])),
          })
        })(event)
      }
    >
      {formError && <Alert>{formError}</Alert>}

      <Field label="Email" hint="Адрес из приглашения">
        {(control) => <Input {...control} value={email} readOnly />}
      </Field>

      <Field label="Имя" error={errors.full_name?.message}>
        {(control) => (
          <Input {...control} {...register('full_name')} autoComplete="name" autoFocus />
        )}
      </Field>

      <Field label="Пароль" error={errors.password?.message} hint="Не короче восьми символов">
        {(control) => (
          <PasswordInput {...control} {...register('password')} autoComplete="new-password" />
        )}
      </Field>

      <Button type="submit" className="w-full" disabled={accept.isPending}>
        {accept.isPending ? 'Принимаем…' : 'Создать учётную запись и принять'}
      </Button>
    </form>
  )
}
