import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { applyServerError } from '@/features/auth/model/server-errors'
import { useCreateWorkspace } from '@/features/workspaces/api/workspaces'
import { slugify } from '@/features/workspaces/model/slug'
import type { WorkspaceRead } from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'

// Те же ограничения, что у бэкенда: SLUG_PATTERN в workspaces/schemas.py.
const schema = z.object({
  name: z.string().trim().min(1, 'Назовите пространство').max(200),
  slug: z
    .string()
    .trim()
    .regex(/^[a-z0-9-]{2,40}$/, 'Строчные латинские буквы, цифры и дефис, от 2 до 40 символов'),
})

type Values = z.infer<typeof schema>

export function CreateWorkspaceForm({ onCreated }: { onCreated: (space: WorkspaceRead) => void }) {
  const create = useCreateWorkspace()
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    setValue,
    getFieldState,
    setError,
    formState: { errors },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: '', slug: '' } })

  const name = register('name')

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) =>
        void handleSubmit((values) => {
          setFormError(null)
          create.mutate(values, {
            onSuccess: onCreated,
            onError: (error) => setFormError(applyServerError(error, setError, ['name', 'slug'])),
          })
        })(event)
      }
    >
      {formError && <Alert>{formError}</Alert>}
      <Field label="Название" error={errors.name?.message}>
        {(control) => (
          <Input
            {...control}
            {...name}
            autoFocus
            onChange={(event) => {
              void name.onChange(event)
              // Пока slug не трогали руками, он следует за названием.
              if (!getFieldState('slug').isDirty) {
                setValue('slug', slugify(event.target.value))
              }
            }}
          />
        )}
      </Field>
      <Field label="Адрес" error={errors.slug?.message} hint="Часть ссылки: /w/адрес">
        {(control) => <Input {...control} {...register('slug')} autoComplete="off" />}
      </Field>
      <Button type="submit" disabled={create.isPending}>
        Создать пространство
      </Button>
    </form>
  )
}
