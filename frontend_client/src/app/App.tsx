import { ThemeProvider } from '../shared/theme/ThemeProvider'
import { ThemeToggle } from '../shared/theme/ThemeToggle'

/**
 * Оболочка приложения: шапка, боковая навигация, область контента.
 *
 * Пока статическая разметка — маршрутизация, клиент запросов и реальные экраны
 * приходят на этапе 5 и встраиваются в эти же три слота.
 */
export function App() {
  return (
    <ThemeProvider>
      <div className="bg-canvas text-fg flex h-full flex-col">
        <header
          role="banner"
          className="border-border bg-surface flex h-14 shrink-0 items-center gap-3 border-b px-4"
        >
          <span className="text-lg font-semibold tracking-tight">TasKanLine</span>
          <span className="bg-surface-hover text-fg-muted rounded-full px-2 py-0.5 text-xs">
            этап 0
          </span>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <nav
            aria-label="Основная навигация"
            className="border-border bg-surface hidden w-56 shrink-0 border-r p-4 sm:block"
          >
            <ul className="text-fg-muted space-y-1 text-sm">
              <li className="hover:bg-surface-hover rounded px-2 py-1.5">Задачи</li>
              <li className="hover:bg-surface-hover rounded px-2 py-1.5">Проекты</li>
              <li className="hover:bg-surface-hover rounded px-2 py-1.5">Views</li>
            </ul>
          </nav>

          <main className="min-w-0 flex-1 overflow-auto p-6">
            <h1 className="text-xl font-medium">Каркас готов</h1>
            <p className="text-fg-muted mt-2 max-w-prose text-sm">
              Бэкенд отвечает на <code className="bg-surface-hover rounded px-1">/health</code>,
              миграции применяются, тесты зелёные. Экраны появляются на этапе 5.
            </p>
          </main>
        </div>
      </div>
    </ThemeProvider>
  )
}
