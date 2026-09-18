import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * Корень никуда не ведёт сам по себе: экранов задач до этапа 3 нет, и человеку
 * здесь нужен профиль. Аутентификацию проверит защищённая ветка маршрутов.
 */
export const Route = createFileRoute('/')({
  beforeLoad: () => {
    throw redirect({ to: '/login' })
  },
})
