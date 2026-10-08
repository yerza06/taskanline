import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { useReauth } from '@/app/reauth'
import { SESSION_KEY } from '@/app/session'
import { apiFetch } from '@/shared/api/client'
import { humanMessage } from '@/shared/api/messages'
import type { AdminSession } from '@/shared/api/types'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { Field } from '@/shared/ui/Field'
import { Input } from '@/shared/ui/Input'

/** Повторный ввод пароля перед опасным действием: окно открыто 15 минут после успеха. */
export function ReauthDialog() {
  const open = useReauth((state) => state.open)
  const finish = useReauth((state) => state.finish)
  const queryClient = useQueryClient()
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [pending, setPending] = useState(false)

  function close(confirmed: boolean) {
    setPassword('')
    setError(null)
    finish(confirmed)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !next && close(false)}
      title="Подтвердите паролем"
      description="Опасное действие. После подтверждения следующие 15 минут пароль спрашиваться не будет."
    >
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          setPending(true)
          setError(null)
          apiFetch<AdminSession>('/admin/reauth', { method: 'POST', json: { password } })
            .then((session) => {
              queryClient.setQueryData(SESSION_KEY, session)
              close(true)
            })
            .catch((failure: unknown) => {
              setError(failure)
              setPassword('')
              if (failure instanceof Error && 'code' in failure && failure.code === 'session_terminated') {
                window.location.reload()
              }
            })
            .finally(() => setPending(false))
        }}
      >
        {error !== null && <Alert>{humanMessage(error)}</Alert>}
        <Field label="Пароль">
          {(control) => (
            <Input
              {...control}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
            />
          )}
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => close(false)}>
            Отмена
          </Button>
          <Button type="submit" disabled={pending || !password}>
            Подтвердить
          </Button>
        </div>
      </form>
    </Dialog>
  )
}
