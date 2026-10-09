import { useTheme } from './theme-context'

const LABELS = {
  light: 'Светлая тема',
  dark: 'Тёмная тема',
} as const

/** Переключатель светлой и тёмной темы. Системный режим остаётся значением по умолчанию. */
export function ThemeToggle() {
  const { theme, setPreference } = useTheme()

  return (
    <button
      type="button"
      onClick={() => setPreference(theme === 'dark' ? 'light' : 'dark')}
      aria-label={`${LABELS[theme]}. Переключить`}
      title={`${LABELS[theme]}. Переключить`}
      className="border-border text-fg-muted hover:bg-surface-hover focus-visible:outline-accent rounded-md border p-2 transition focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      <span aria-hidden="true">{theme === 'dark' ? '☾' : '☀'}</span>
    </button>
  )
}
