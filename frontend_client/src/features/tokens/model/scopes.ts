import type { TokenScope } from '@/shared/api/types'

export const SCOPE_LABELS: Record<TokenScope, string> = {
  read: 'Только чтение',
  read_write: 'Чтение и запись',
}

export const SCOPE_HINTS: Record<TokenScope, string> = {
  read: 'Агент видит задачи и проекты, но ничего не меняет',
  read_write: 'Агент создаёт и меняет задачи от вашего имени',
}
