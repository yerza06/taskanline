import { requestReauth } from '@/app/reauth'

import { ApiError, apiFetch, type RequestOptions } from './client'

/**
 * Запрос к `/admin/*`: опасное действие без свежего подтверждения паролем
 * открывает окно ввода пароля и после успеха повторяется само — один раз.
 */
export async function adminFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  try {
    return await apiFetch<T>(`/admin${path}`, options)
  } catch (error) {
    if (error instanceof ApiError && error.code === 'reauth_required' && (await requestReauth())) {
      return apiFetch<T>(`/admin${path}`, options)
    }
    throw error
  }
}
