import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { applyServerError } from '@/features/auth/model/server-errors'
import { useCreateProject } from '@/features/projects/api/projects'
import type { ProjectRead } from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'

const schema = z.object({
  name: z.string().trim().min(1, 'Назовите проект').max(200),
  target_date: z.string(),
})

type Values = z.infer<typeof schema>

export function CreateProjectDialog({
  teamId,
  teamKey,
  open,
  onOpenChange,
  onCreated,
}: {
  teamId: string
  teamKey: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (project: ProjectRead) => void
}) {
  const create = useCreateProject(teamId)
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: '', target_date: '' } })

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Новый проект в ${teamKey}`}
      description="Проект собирает задачи команды вокруг одной цели и срока."
    >
      <form
        noValidate
        className="space-y-4"
        onSubmit={(event) =>
          void handleSubmit((values) => {
            setFormError(null)
            create.mutate(
              { name: values.name, status: 'planned', target_date: values.target_date || null },
              {
                onSuccess: (project) => {
                  reset()
                  onCreated(project)
                },
                onError: (error) => setFormError(applyServerError(error, setError, ['name'])),
              },
            )
          })(event)
        }
      >
        {formError && <Alert>{formError}</Alert>}
        <Field label="Название" error={errors.name?.message}>
          {(control) => <Input {...control} {...register('name')} autoFocus />}
        </Field>
        <Field label="Целевая дата" hint="Необязательно">
          {(control) => <Input {...control} {...register('target_date')} type="date" />}
        </Field>
        <Button type="submit" disabled={create.isPending}>
          Создать проект
        </Button>
      </form>
    </Dialog>
  )
}
