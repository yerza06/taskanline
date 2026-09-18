import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { canWrite, useSession } from '@/features/auth/api/session'
import { tokensQueryOptions, useRevokeToken } from '@/features/tokens/api/tokens'
import { CreateTokenForm } from '@/features/tokens/components/CreateTokenForm'
import { CreatedTokenDialog } from '@/features/tokens/components/CreatedTokenDialog'
import { RevokeTokenDialog } from '@/features/tokens/components/RevokeTokenDialog'
import { SCOPE_LABELS } from '@/features/tokens/model/scopes'
import type { TokenRead } from '@/shared/api/types'
import { formatDateTime } from '@/shared/lib/format'
import { Button } from '@/shared/ui/Button'

export function TokensPage() {
  const session = useSession()
  const tokens = useQuery(tokensQueryOptions())
  const revoke = useRevokeToken()
  const [issued, setIssued] = useState<string | null>(null)
  const [revoking, setRevoking] = useState<TokenRead | null>(null)

  const items = tokens.data?.items ?? []

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 p-4 sm:p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Токены доступа</h1>
        <p className="text-fg-muted mt-1 max-w-prose text-sm">
          Токен заменяет пароль для агента и командной строки. Он действует от вашего имени, но
          только в пределах выданной области.
        </p>
      </div>

      <section className="border-border bg-surface rounded-lg border p-4 sm:p-6">
        <h2 className="text-fg-muted text-xs tracking-wide uppercase">Выпущенные</h2>

        {items.length === 0 ? (
          <p className="text-fg-muted mt-3 text-sm">
            Пока не выпущено ни одного токена.
          </p>
        ) : (
          <ul className="divide-border mt-3 divide-y">
            {items.map((token) => (
              <li key={token.id} className="flex flex-wrap items-start gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm">{token.name}</p>
                  <p className="text-fg-muted mt-0.5 text-xs">
                    <code>{token.prefix}</code> · {SCOPE_LABELS[token.scope]} ·{' '}
                    {token.last_used_at
                      ? `использован ${formatDateTime(token.last_used_at)}`
                      : 'ни разу не использован'}
                  </p>
                </div>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setRevoking(token)}
                  disabled={!canWrite(session)}
                >
                  Отозвать
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <CreateTokenForm onCreated={setIssued} />

      <CreatedTokenDialog token={issued} onClose={() => setIssued(null)} />
      <RevokeTokenDialog
        token={revoking}
        pending={revoke.isPending}
        onCancel={() => setRevoking(null)}
        onConfirm={() => {
          if (revoking) {
            revoke.mutate(revoking.id, { onSettled: () => setRevoking(null) })
          }
        }}
      />
    </div>
  )
}
