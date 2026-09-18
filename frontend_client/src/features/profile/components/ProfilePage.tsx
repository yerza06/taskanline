import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { canWrite, useLogout, useSession } from '@/features/auth/api/session'
import { ROLE_LABELS } from '@/features/auth/model/roles'
import { applyServerError } from '@/features/auth/model/server-errors'
import { useUpdateProfile } from '@/features/profile/api/profile'
import { ThemeSelector } from '@/features/profile/components/ThemeSelector'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'

const profileSchema = z.object({
  full_name: z.string().trim().min(1, 'Укажите имя').max(200, 'Имя длиннее 200 символов'),
  avatar_url: z.string().trim().max(2000, 'Ссылка длиннее 2000 символов'),
})

type ProfileValues = z.infer<typeof profileSchema>

export function ProfilePage() {
  const session = useSession()
  const update = useUpdateProfile()
  const logout = useLogout()
  const [formError, setFormError] = useState<string | null>(null)
  const editable = canWrite(session)

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: { full_name: '', avatar_url: '' },
  })

  // Данные приходят из кэша сессии и могут обновиться в фоне — форма следует
  // за ними, пока человек не начал править.
  useEffect(() => {
    if (session) {
      reset({ full_name: session.full_name, avatar_url: session.avatar_url ?? '' })
    }
  }, [session, reset])

  if (!session) {
    return null
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-8 p-4 sm:p-6">
      <h1 className="text-xl font-medium">Профиль</h1>

      <section className="border-border bg-surface space-y-3 rounded-lg border p-4 sm:p-6">
        <h2 className="text-fg-muted text-xs tracking-wide uppercase">Учётная запись</h2>
        <dl className="grid gap-3 sm:grid-cols-2">
          <div>
            <dt className="text-fg-muted text-xs">Email</dt>
            <dd className="text-sm break-all">{session.email}</dd>
          </div>
          <div>
            <dt className="text-fg-muted text-xs">Роль инстанса</dt>
            <dd className="text-sm">{ROLE_LABELS[session.role]}</dd>
          </div>
        </dl>
        <p className="text-fg-muted text-xs">
          Email и роль инстанса из профиля не меняются: роль назначает администратор.
        </p>
      </section>

      <form
        noValidate
        className="border-border bg-surface space-y-4 rounded-lg border p-4 sm:p-6"
        onSubmit={(event) =>
          void handleSubmit((values) => {
            setFormError(null)
            update.mutate(
              { full_name: values.full_name, avatar_url: values.avatar_url || null },
              {
                onError: (error) => {
                  setFormError(applyServerError(error, setError, ['full_name', 'avatar_url']))
                },
              },
            )
          })(event)
        }
      >
        <h2 className="text-fg-muted text-xs tracking-wide uppercase">О себе</h2>

        {formError && <Alert>{formError}</Alert>}

        <Field label="Имя" error={errors.full_name?.message}>
          {(control) => <Input {...control} {...register('full_name')} disabled={!editable} />}
        </Field>

        <Field
          label="Ссылка на аватар"
          error={errors.avatar_url?.message}
          hint="Можно оставить пустым"
        >
          {(control) => (
            <Input {...control} {...register('avatar_url')} type="url" disabled={!editable} />
          )}
        </Field>

        <Button type="submit" disabled={!editable || update.isPending}>
          Сохранить
        </Button>

        {!editable && (
          <p className="text-fg-muted text-xs">
            Токен доступа выдан только на чтение — изменения недоступны.
          </p>
        )}
      </form>

      <section className="border-border bg-surface space-y-3 rounded-lg border p-4 sm:p-6">
        <h2 className="text-fg-muted text-xs tracking-wide uppercase">Оформление</h2>
        <ThemeSelector />
      </section>

      <section className="border-border bg-surface flex flex-wrap items-center gap-3 rounded-lg border p-4 sm:p-6">
        <div className="min-w-0 flex-1">
          <h2 className="text-fg-muted text-xs tracking-wide uppercase">Сессия</h2>
          <p className="text-fg-muted mt-1 text-sm">
            Выход закрывает эту сессию. Токены доступа продолжат работать.
          </p>
        </div>
        <Button variant="secondary" onClick={() => logout.mutate()} disabled={logout.isPending}>
          Выйти
        </Button>
      </section>
    </div>
  )
}
