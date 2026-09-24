import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { applyServerError } from '@/features/auth/model/server-errors'
import { useCreateToken } from '@/features/tokens/api/tokens'
import { SCOPE_HINTS, SCOPE_LABELS } from '@/features/tokens/model/scopes'
import type { TokenScope } from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'

const schema = z.object({
  name: z.string().trim().min(1, 'Дайте токену имя').max(100, 'Имя длиннее 100 символов'),
  scope: z.enum(['read', 'read_write']),
  expires_on: z.string(),
})

type Values = z.infer<typeof schema>

const SCOPES: TokenScope[] = ['read', 'read_write']

export function CreateTokenForm({ onCreated }: { onCreated: (token: string) => void }) {
  const create = useCreateToken()
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', scope: 'read', expires_on: '' },
  })

  return (
    <form
      noValidate
      className="border-border bg-surface space-y-4 rounded-lg border p-4 sm:p-6"
      onSubmit={(event) =>
        void handleSubmit((values) => {
          setFormError(null)
          create.mutate(
            {
              name: values.name,
              scope: values.scope,
              // Пустая дата — бессрочный токен; так же это читает бэкенд.
              expires_at: values.expires_on ? new Date(values.expires_on).toISOString() : null,
            },
            {
              onSuccess: (token) => {
                reset()
                onCreated(token.token)
              },
              onError: (error) => {
                setFormError(applyServerError(error, setError, ['name', 'scope']))
              },
            },
          )
        })(event)
      }
    >
      <h2 className="text-fg-muted text-xs tracking-wide uppercase">Новый токен</h2>

      {formError && <Alert>{formError}</Alert>}

      <Field label="Название" error={errors.name?.message} hint="Например, имя агента или машины">
        {(control) => <Input {...control} {...register('name')} autoComplete="off" />}
      </Field>

      <fieldset className="space-y-2">
        <legend className="text-fg block text-sm font-medium">Что разрешено</legend>
        {SCOPES.map((scope) => (
          <label key={scope} className="flex items-start gap-2">
            <input type="radio" value={scope} {...register('scope')} className="mt-1" />
            <span>
              <span className="block text-sm">{SCOPE_LABELS[scope]}</span>
              <span className="text-fg-muted block text-xs">{SCOPE_HINTS[scope]}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <Field label="Действует до" error={errors.expires_on?.message} hint="Пусто — бессрочный">
        {(control) => <Input {...control} {...register('expires_on')} type="date" />}
      </Field>

      <Button type="submit" disabled={create.isPending}>
        Выпустить токен
      </Button>
    </form>
  )
}
