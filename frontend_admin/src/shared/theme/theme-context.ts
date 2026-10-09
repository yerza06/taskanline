import { createContext, use } from 'react'

import type { ResolvedTheme, ThemePreference } from './theme'

export interface ThemeContextValue {
  /** Что выбрал пользователь: light, dark или system. */
  preference: ThemePreference
  /** Что применено на самом деле после раскрытия system. */
  theme: ResolvedTheme
  setPreference: (preference: ThemePreference) => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function useTheme(): ThemeContextValue {
  const value = use(ThemeContext)
  if (!value) {
    throw new Error('useTheme вызван вне ThemeProvider')
  }
  return value
}
