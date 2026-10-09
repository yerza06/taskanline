import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { useCan } from '@/app/session'
import { adminFetch } from '@/shared/api/admin'
import { humanMessage } from '@/shared/api/messages'
import type { RegistrationMode, SettingsRead, SettingsUpdate } from '@/shared/api/types'
import { MODE_LABELS } from '@/shared/lib/labels'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'
import { PageTitle } from '@/shared/ui/Page'
import { Select } from '@/shared/ui/Select'

function Form({ initial, editable }: { initial: SettingsRead; editable: boolean }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(initial.instance_name)
  const [mode, setMode] = useState<RegistrationMode>(initial.registration_mode)
  const [domains, setDomains] = useState(initial.allowed_email_domains.join(', '))
  const [ttl, setTtl] = useState(String(initial.invitation_ttl_days))
  const [maintenance, setMaintenance] = useState(initial.maintenance_mode)
  const [saved, setSaved] = useState(false)
  const save = useMutation({
    mutationFn: (values: SettingsUpdate) =>
      adminFetch<SettingsRead>('/settings', { method: 'PATCH', json: values }),
    onSuccess: (settings) => {
      queryClient.setQueryData(['settings'], settings)
      setSaved(true)
    },
  })

  return (
    <form
      className="border-border bg-surface max-w-2xl space-y-5 rounded-lg border p-4 sm:p-6"
      onSubmit={(e) => {
        e.preventDefault()
        setSaved(false)
        save.mutate({
          instance_name: name.trim(),
          registration_mode: mode,
          allowed_email_domains: domains
            .split(/[\s,]+/)
            .map((d) => d.trim())
            .filter(Boolean),
          invitation_ttl_days: Number(ttl),
          maintenance_mode: maintenance,
        })
      }}
    >
      {save.error && <Alert>{humanMessage(save.error)}</Alert>}
      {saved && (
        <p role="status" className="text-sm">
          Сохранено.
        </p>
      )}
      <fieldset disabled={!editable} className="space-y-5">
        <Field label="Название инстанса" hint="Заголовок в интерфейсе и в письмах">
          {(control) => <Input {...control} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Регистрация" hint="Кто может завести учётную запись сам, без приглашения">
          {(control) => (
            <Select
              {...control}
              className="w-full"
              value={mode}
              onChange={(e) => setMode(e.target.value as RegistrationMode)}
            >
              {(Object.keys(MODE_LABELS) as RegistrationMode[]).map((value) => (
                <option key={value} value={value}>
                  {MODE_LABELS[value]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {mode === 'open' && (
          <p role="note" className="border-fg rounded-md border border-l-4 px-3 py-2 text-sm font-semibold">
            Сервер станет доступен для самостоятельной регистрации любому, кто до него дотянется.
          </p>
        )}
        {mode === 'domain_allowlist' && (
          <Field label="Разрешённые домены" hint="Через запятую: acme.com, acme.io. Поддомены не входят.">
            {(control) => <Input {...control} value={domains} onChange={(e) => setDomains(e.target.value)} />}
          </Field>
        )}
        <Field label="Срок жизни приглашения, дней" hint="От 1 до 365; действует для новых приглашений">
          {(control) => (
            <Input {...control} type="number" min={1} max={365} value={ttl} onChange={(e) => setTtl(e.target.value)} />
          )}
        </Field>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={maintenance} onChange={(e) => setMaintenance(e.target.checked)} />
          <span>
            <span className="block font-medium">Режим обслуживания</span>
            <span className="text-fg-muted block">
              Все, кроме ролей инстанса, получают «сервер на обслуживании». Агенты тоже.
            </span>
          </span>
        </label>
        {editable && (
          <Button type="submit" disabled={save.isPending}>
            Сохранить
          </Button>
        )}
      </fieldset>
    </form>
  )
}

export function SettingsPage() {
  const editable = useCan('superadmin')
  const settings = useQuery({ queryKey: ['settings'], queryFn: () => adminFetch<SettingsRead>('/settings') })
  return (
    <>
      <PageTitle
        title="Настройки инстанса"
        hint={editable ? 'Изменение подтверждается паролем.' : 'Менять настройки может только суперадминистратор.'}
      />
      {settings.data && <Form initial={settings.data} editable={editable} />}
    </>
  )
}
