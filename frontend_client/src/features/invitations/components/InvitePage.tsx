import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'

import { sessionQueryOptions } from '@/features/auth/api/session'
import { AuthLayout } from '@/features/auth/components/AuthLayout'
import {
  invitationPreviewQueryOptions,
  useAcceptInvitation,
} from '@/features/invitations/api/invitations'
import { AcceptInvitationForm } from '@/features/invitations/components/AcceptInvitationForm'
import { CLOSED, roleLabel, scopeLabel } from '@/features/invitations/model/labels'
import { humanMessage } from '@/shared/api/messages'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'

const TITLE = 'Приглашение'

/**
 * Страница из письма. Открыта без входа: приглашённого в системе может ещё не
 * быть, и тогда учётная запись заводится прямо здесь.
 */
export function InvitePage({ token }: { token: string }) {
  const preview = useQuery(invitationPreviewQueryOptions(token))
  // 401 здесь — не ошибка, а «не вошёл»: страница показывает форму регистрации.
  const session = useQuery(sessionQueryOptions())

  const signIn = (
    <>
      Уже есть учётная запись?{' '}
      <Link
        to="/login"
        search={{ redirect: `/invite/${token}` }}
        className="text-accent underline underline-offset-4"
      >
        Войти
      </Link>
    </>
  )

  if (preview.isPending || session.isPending) {
    return (
      <AuthLayout title={TITLE} description="Загружаем приглашение…" footer={null}>
        {null}
      </AuthLayout>
    )
  }

  if (preview.isError) {
    return (
      <AuthLayout title={TITLE} description="Ссылка не сработала" footer={signIn}>
        <Alert>{humanMessage(preview.error)}</Alert>
      </AuthLayout>
    )
  }

  const invitation = preview.data
  const description = `${invitation.inviter_name} приглашает вас в «${invitation.workspace_name}»`

  if (invitation.status !== 'pending') {
    return (
      <AuthLayout title={TITLE} description={description} footer={signIn}>
        <Alert>{CLOSED[invitation.status]}</Alert>
      </AuthLayout>
    )
  }

  const me = session.data
  const sameEmail = me?.email.toLowerCase() === invitation.email.toLowerCase()

  return (
    <AuthLayout title={TITLE} description={description} footer={me ? null : signIn}>
      <p className="text-fg-muted mb-4 text-sm">
        Доступ: {scopeLabel(invitation.scope_type)}, роль — {roleLabel(invitation.role)}.
      </p>

      {!me && <AcceptInvitationForm token={token} email={invitation.email} />}
      {me && sameEmail && <AcceptAsSignedIn token={token} />}
      {me && !sameEmail && (
        <Alert>
          Приглашение отправлено на {invitation.email}, а вы вошли как {me.email}. Войдите под
          нужной учётной записью.
        </Alert>
      )}
    </AuthLayout>
  )
}

function AcceptAsSignedIn({ token }: { token: string }) {
  const accept = useAcceptInvitation(token)
  const [error, setError] = useState<string | null>(null)

  return (
    <div className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <Button
        className="w-full"
        disabled={accept.isPending}
        onClick={() => {
          setError(null)
          accept.mutate(undefined, { onError: (failure) => setError(humanMessage(failure)) })
        }}
      >
        {accept.isPending ? 'Принимаем…' : 'Принять приглашение'}
      </Button>
    </div>
  )
}
