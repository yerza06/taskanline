/**
 * Оболочка приложения: шапка, боковая навигация, область контента.
 *
 * Пока статическая разметка — маршрутизация, клиент запросов и реальные экраны
 * приходят на этапе 5 и встраиваются в эти же три слота.
 */
export function App() {
  return (
    <div className="flex h-full flex-col bg-slate-50 text-slate-900">
      <header
        role="banner"
        className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4"
      >
        <span className="text-lg font-semibold tracking-tight">TasKanLine</span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
          этап 0
        </span>
      </header>

      <div className="flex min-h-0 flex-1">
        <nav
          aria-label="Основная навигация"
          className="hidden w-56 shrink-0 border-r border-slate-200 bg-white p-4 sm:block"
        >
          <ul className="space-y-1 text-sm text-slate-600">
            <li className="rounded px-2 py-1.5 hover:bg-slate-100">Задачи</li>
            <li className="rounded px-2 py-1.5 hover:bg-slate-100">Проекты</li>
            <li className="rounded px-2 py-1.5 hover:bg-slate-100">Views</li>
          </ul>
        </nav>

        <main className="min-w-0 flex-1 overflow-auto p-6">
          <h1 className="text-xl font-medium">Каркас готов</h1>
          <p className="mt-2 max-w-prose text-sm text-slate-600">
            Бэкенд отвечает на <code className="rounded bg-slate-200 px-1">/health</code>,
            миграции применяются, тесты зелёные. Экраны появляются на этапе 5.
          </p>
        </main>
      </div>
    </div>
  )
}
