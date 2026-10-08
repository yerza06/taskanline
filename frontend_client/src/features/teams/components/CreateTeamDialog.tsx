import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { applyServerError } from '@/features/auth/model/server-errors'
import { useCreateTeam } from '@/features/teams/api/teams'
import type { TeamRead } from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'

// KEY_PATTERN бэкенда: ключ — префикс номеров задач, ENG-142.
const schema = z.object({
  key: z
    .string()
    .trim()
    .toUpperCase()
    .regex(/^[A-Z]{2,5}$/, 'От 2 до 5 латинских букв, например ENG'),
  name: z.string().trim().min(1, 'Назовите команду').max(200),
  is_private: z.boolean(),
})

type Values = z.infer<typeof schema>

export function CreateTeamDialog({
  workspaceId,
  open,
  onOpenChange,
  onCreated,
}: {
  workspaceId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (team: TeamRead) => void
}) {
  const create = useCreateTeam(workspaceId)
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { key: '', name: '', is_private: false },
  })

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Новая команда"
      description="Ключ команды станет префиксом номеров её задач: ENG-1, ENG-2…"
    >
      <form
        noValidate
        className="space-y-4"
        onSubmit={(event) =>
          void handleSubmit((values) => {
            setFormError(null)
            create.mutate(values, {
              onSuccess: (team) => {
                reset()
                onCreated(team)
              },
              onError: (error) =>
                setFormError(applyServerError(error, setError, ['key', 'name'])),
            })
          })(event)
        }
      >
        {formError && <Alert>{formError}</Alert>}
        <Field label="Название" error={errors.name?.message}>
          {(control) => <Input {...control} {...register('name')} autoFocus />}
        </Field>
        <Field label="Ключ" error={errors.key?.message}>
          {(control) => (
            <Input {...control} {...register('key')} className="uppercase" autoComplete="off" />
          )}
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" {...register('is_private')} />
          Закрытая — видна только участникам
        </label>
        <Button type="submit" disabled={create.isPending}>
          Создать команду
        </Button>
      </form>
    </Dialog>
  )
}
