import { create } from 'zustand'

/**
 * Состояние интерфейса, которое переживает смену экрана: открытое меню на
 * телефоне, окно быстрого создания задачи, справка по клавишам. Данные с
 * сервера здесь не живут — они в кэше TanStack Query.
 */
interface UiState {
  sidebarOpen: boolean
  quickCreateOpen: boolean
  helpOpen: boolean
  setSidebarOpen: (open: boolean) => void
  setQuickCreateOpen: (open: boolean) => void
  setHelpOpen: (open: boolean) => void
}

export const useUi = create<UiState>((set) => ({
  sidebarOpen: false,
  quickCreateOpen: false,
  helpOpen: false,
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setQuickCreateOpen: (quickCreateOpen) => set({ quickCreateOpen }),
  setHelpOpen: (helpOpen) => set({ helpOpen }),
}))
