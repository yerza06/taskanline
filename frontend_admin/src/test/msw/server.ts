import { setupServer } from 'msw/node'

import { defaultHandlers } from './handlers'

/**
 * Сеть в тестах не поднимается: запросы перехватывает MSW.
 *
 * Обработчики по умолчанию описывают аутентифицированного пользователя —
 * это состояние, в котором живёт большинство экранов. Тест, которому нужно
 * другое, объявляет это явно через `server.use(...)`.
 */
export const server = setupServer(...defaultHandlers())
