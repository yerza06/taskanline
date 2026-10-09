import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { ThemeContext } from './theme-context'
import {
  applyTheme,
  readStoredPreference,
  storePreference,
  systemTheme,
  type ResolvedTheme,
  type ThemePreference,
} from './theme'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStoredPreference)
  const [system, setSystem] = useState<ResolvedTheme>(systemTheme)

  // Применённая тема — производная от двух состояний, а не третье состояние:
  // отдельный useState здесь дал бы лишний рендер и шанс разъехаться.
  const theme: ResolvedTheme = preference === 'system' ? system : preference

  // Единственная настоящая синхронизация с внешним миром — класс на <html>.
  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => {
    const media = globalThis.matchMedia?.('(prefers-color-scheme: dark)')
    if (!media) {
      return
    }
    const onChange = (event: MediaQueryListEvent) => {
      setSystem(event.matches ? 'dark' : 'light')
    }
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  const setPreference = useCallback((next: ThemePreference) => {
    storePreference(next)
    setPreferenceState(next)
  }, [])

  const value = useMemo(
    () => ({ preference, theme, setPreference }),
    [preference, theme, setPreference],
  )

  return <ThemeContext value={value}>{children}</ThemeContext>
}
