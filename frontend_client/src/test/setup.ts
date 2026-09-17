import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'

/** jsdom не реализует matchMedia — без заглушки падает любой код, читающий системную тему. */
export function mockPrefersColorScheme(prefersDark: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>()

  const mediaQueryList = {
    matches: prefersDark,
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener)
    },
    removeEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.delete(listener)
    },
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }

  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => mediaQueryList),
  )

  return {
    /** Сымитировать смену системной темы. */
    emit(matches: boolean) {
      mediaQueryList.matches = matches
      for (const listener of listeners) {
        listener({ matches } as MediaQueryListEvent)
      }
    },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  document.documentElement.classList.remove('dark')
  document.documentElement.removeAttribute('data-theme')
})

mockPrefersColorScheme(false)
