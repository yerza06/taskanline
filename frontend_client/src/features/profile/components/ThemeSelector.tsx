import { useTheme } from '@/shared/theme/theme-context'
import type { ThemePreference } from '@/shared/theme/theme'

const OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: 'light', label: 'Светлая' },
  { value: 'dark', label: 'Тёмная' },
  { value: 'system', label: 'Системная' },
]

/**
 * Выбор темы из трёх состояний.
 *
 * Переключатель в шапке меняет светлую на тёмную одним нажатием; вернуть
 * «как в системе» можно только здесь — и это единственное место, где выбор
 * виден целиком.
 */
export function ThemeSelector() {
  const { preference, setPreference } = useTheme()

  return (
    <div className="flex gap-2">
      {OPTIONS.map((option) => (
        <label key={option.value} className="flex-1">
          <input
            type="radio"
            name="theme"
            className="peer sr-only"
            checked={preference === option.value}
            onChange={() => setPreference(option.value)}
          />
          <span className="border-border peer-checked:border-accent peer-checked:text-accent peer-focus-visible:outline-accent hover:bg-surface-hover block cursor-pointer rounded-md border px-3 py-1.5 text-center text-sm transition peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2">
            {option.label}
          </span>
        </label>
      ))}
    </div>
  )
}
