import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * Корень никуда не ведёт сам по себе: экранов задач до этапа 3 нет, и человеку
 * здесь нужен профиль. Не вошедшего развернёт защита маршрутов.
 */
export const Route = createFileRoute('/')({
  beforeLoad: () => {
    throw redirect({ to: '/profile' })
  },
})
