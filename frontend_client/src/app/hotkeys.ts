import { useNavigate, useParams } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'

import { useUi } from '@/app/ui-store'
import { canWrite, useSession } from '@/features/auth/api/session'
import { useTeams } from '@/features/teams/api/teams'
import type { WorkspaceRead } from '@/shared/api/types'

export const SHORTCUTS: [string, string][] = [
  ['c', 'Создать задачу'],
  ['/', 'Поиск: фильтр по названию'],
  ['g t', 'Перейти к команде'],
  ['g i', 'Входящие'],
  ['g m', 'Мои задачи'],
  ['?', 'Эта справка'],
]

/** Набирает ли человек текст — тогда буквы принадлежат полю, а не горячим клавишам. */
function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

/**
 * Горячие клавиши пространства. Срабатывают, только когда фокус не в поле ввода
 * и не открыто модальное окно, и без модификаторов — Ctrl+C остаётся копированием.
 */
export function useHotkeys(workspace: WorkspaceRead) {
  const navigate = useNavigate()
  const params = useParams({ strict: false })
  const teams = useTeams(workspace.id).data
  const writable = canWrite(useSession())
  const { setQuickCreateOpen, setHelpOpen } = useUi.getState()
  const pendingG = useRef(false)

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
      if (typing(event.target) || document.querySelector('[role="dialog"]')) return

      if (pendingG.current) {
        pendingG.current = false
        const list = teams ?? []
        const team = list.find((t) => t.key === params.key?.toUpperCase()) ?? list[0]
        if (event.key === 't' && team) {
          event.preventDefault()
          void navigate({ to: '/w/$workspace/team/$key', params: { workspace: workspace.slug, key: team.key }, search: {} })
        } else if (event.key === 'i') {
          event.preventDefault()
          void navigate({ to: '/w/$workspace/inbox', params: { workspace: workspace.slug } })
        } else if (event.key === 'm') {
          event.preventDefault()
          void navigate({ to: '/w/$workspace', params: { workspace: workspace.slug } })
        }
        return
      }

      switch (event.key) {
        case 'c':
          if (writable) {
            event.preventDefault()
            setQuickCreateOpen(true)
          }
          break
        case '?':
          event.preventDefault()
          setHelpOpen(true)
          break
        case 'g':
          pendingG.current = true
          // Вторая клавиша — в пределах секунды, иначе «g» просто забывается.
          window.setTimeout(() => (pendingG.current = false), 1000)
          break
        case '/': {
          event.preventDefault()
          focusSearch()
          break
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate, params.key, setHelpOpen, setQuickCreateOpen, teams, workspace.slug, writable])
}

/** `/` — к поиску по названию: открыть фильтры, добавить условие и поставить фокус. */
function focusSearch() {
  const input = document.querySelector<HTMLInputElement>('input[aria-label="Значение: Название"]')
  if (input) {
    input.focus()
    return
  }
  window.dispatchEvent(new CustomEvent('tkl:search'))
}
