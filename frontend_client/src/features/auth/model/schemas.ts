import { z } from 'zod'

/**
 * Схемы форм аутентификации.
 *
 * Ограничения повторяют серверные (`RegisterRequest` в backend): проверка на
 * клиенте экономит человеку запрос, но не заменяет серверную — та остаётся
 * единственной, которой можно верить.
 */

const email = z.string().min(1, 'Укажите email').pipe(z.email('Похоже, это не email'))

export const loginSchema = z.object({
  email,
  password: z.string().min(1, 'Введите пароль'),
})

export const registerSchema = z.object({
  email,
  full_name: z.string().trim().min(1, 'Укажите имя').max(200, 'Имя длиннее 200 символов'),
  password: z
    .string()
    .min(8, 'Пароль короче восьми символов')
    .max(128, 'Пароль длиннее 128 символов'),
})

export type LoginValues = z.infer<typeof loginSchema>
export type RegisterValues = z.infer<typeof registerSchema>
