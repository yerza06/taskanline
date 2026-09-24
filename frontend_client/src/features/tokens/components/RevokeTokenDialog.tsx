import type { TokenRead } from '@/shared/api/types'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'

/**
 * Подтверждение отзыва.
 *
 * Имя токена названо в тексте: отозвать чужой по ошибке — значит уронить
 * работающего агента, а вернуть значение уже нельзя.
 */
export function RevokeTokenDialog({
  token,
  pending,
  onCancel,
  onConfirm,
}: {
  token: TokenRead | null
  pending: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <Dialog
      open={token !== null}
      onOpenChange={(open) => {
        if (!open) {
          onCancel()
        }
      }}
      title="Отозвать токен?"
      description={
        token
          ? `«${token.name}» перестанет работать сразу. Выпустить его заново с тем же значением нельзя.`
          : ''
      }
    >
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>
          Отмена
        </Button>
        <Button variant="danger" onClick={onConfirm} disabled={pending}>
          Отозвать
        </Button>
      </div>
    </Dialog>
  )
}
