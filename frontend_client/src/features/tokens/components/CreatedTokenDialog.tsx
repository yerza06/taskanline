import { Check, Copy } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'

/**
 * Единственный момент, когда видно полное значение токена: бэкенд хранит
 * только его хеш, и показать значение второй раз неоткуда.
 */
export function CreatedTokenDialog({ token, onClose }: { token: string | null; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const Icon = copied ? Check : Copy

  return (
    <Dialog
      open={token !== null}
      onOpenChange={(open) => {
        if (!open) {
          setCopied(false)
          onClose()
        }
      }}
      title="Токен выпущен"
      description="Скопируйте его сейчас — показать значение второй раз будет неоткуда: сервер хранит только хеш."
    >
      <div className="space-y-4">
        <code className="border-border bg-canvas block rounded-md border p-3 text-xs break-all">
          {token}
        </code>

        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              void navigator.clipboard.writeText(token ?? '').then(() => setCopied(true))
            }}
          >
            <Icon aria-hidden="true" className="size-4" />
            {copied ? 'Скопировано' : 'Скопировать'}
          </Button>
          <Button
            onClick={() => {
              setCopied(false)
              onClose()
            }}
          >
            Готово
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
