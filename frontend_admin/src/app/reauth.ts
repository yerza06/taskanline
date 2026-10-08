import { create } from 'zustand'

/**
 * Окно подтверждения паролем — одно на приложение.
 *
 * Опасный запрос, получивший `403 reauth_required`, вызывает `requestReauth()` и ждёт:
 * окно откроется, человек введёт пароль, и запрос повторится сам. Отмена — запрос
 * завершается исходной ошибкой.
 */
interface ReauthState {
  open: boolean
  resolve: ((confirmed: boolean) => void) | null
  request: () => Promise<boolean>
  finish: (confirmed: boolean) => void
}

export const useReauth = create<ReauthState>((set, get) => ({
  open: false,
  resolve: null,
  request: () =>
    new Promise<boolean>((resolve) => {
      // Второй опасный запрос, пока окно открыто, ждёт того же подтверждения.
      const previous = get().resolve
      set({
        open: true,
        resolve: (confirmed) => {
          previous?.(confirmed)
          resolve(confirmed)
        },
      })
    }),
  finish: (confirmed) => {
    get().resolve?.(confirmed)
    set({ open: false, resolve: null })
  },
}))

export function requestReauth(): Promise<boolean> {
  return useReauth.getState().request()
}
