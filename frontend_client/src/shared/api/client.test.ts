import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { errorBody, ME } from '../../test/msw/handlers'
import { server } from '../../test/msw/server'
import { ApiError, apiFetch, markSessionActive } from './client'
import { fieldErrors, humanMessage } from './messages'

beforeEach(() => {
  // Клиент помнит между запросами, что сессии нет. Тесты не должны наследовать
  // это знание друг от друга.
  markSessionActive()
})

describe('apiFetch', () => {
  it('ходит с cookie и заголовком, который требует защита от CSRF', async () => {
    let seen: Request | undefined
    server.use(
      http.patch('/api/v1/me', ({ request }) => {
        seen = request
        return HttpResponse.json(ME)
      }),
    )

    await apiFetch('/me', { method: 'PATCH', json: { full_name: 'Иван' } })

    expect(seen?.headers.get('X-Requested-With')).toBe('XMLHttpRequest')
    expect(seen?.headers.get('Content-Type')).toBe('application/json')
    expect(seen?.credentials).toBe('include')
  })

  it('разбирает конверт ошибки в ApiError с машиночитаемым кодом', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json(errorBody('invalid_credentials', 'Неверная пара'), { status: 401 }),
      ),
    )

    const error = await apiFetch('/auth/login', { method: 'POST', json: {} }).catch(
      (caught: unknown) => caught,
    )

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(401)
    expect((error as ApiError).code).toBe('invalid_credentials')
  })

  it('возвращает undefined на 204', async () => {
    server.use(http.post('/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 })))

    await expect(apiFetch('/auth/logout', { method: 'POST' })).resolves.toBeUndefined()
  })

  it('обновляет сессию и повторяет запрос после 401', async () => {
    let refreshed = false
    server.use(
      http.post('/api/v1/auth/refresh', () => {
        refreshed = true
        return HttpResponse.json({ user: ME })
      }),
      http.get('/api/v1/me', () => (refreshed ? HttpResponse.json(ME) : unauthorized())),
    )

    await expect(apiFetch('/me')).resolves.toMatchObject({ email: ME.email })
    expect(refreshed).toBe(true)
  })

  it('на два параллельных 401 обновляет сессию один раз', async () => {
    let refreshCalls = 0
    let refreshed = false
    server.use(
      http.post('/api/v1/auth/refresh', async () => {
        refreshCalls += 1
        await delay()
        refreshed = true
        return HttpResponse.json({ user: ME })
      }),
      http.get('/api/v1/me', () => (refreshed ? HttpResponse.json(ME) : unauthorized())),
      http.get('/api/v1/me/tokens', () =>
        refreshed ? HttpResponse.json({ items: [] }) : unauthorized(),
      ),
    )

    await Promise.all([apiFetch('/me'), apiFetch('/me/tokens')])

    expect(refreshCalls).toBe(1)
  })

  it('не пытается обновить сессию ради самого /auth/*', async () => {
    let refreshCalls = 0
    server.use(
      http.post('/api/v1/auth/refresh', () => {
        refreshCalls += 1
        return unauthorized()
      }),
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json(errorBody('invalid_credentials'), { status: 401 }),
      ),
    )

    await expect(apiFetch('/auth/login', { method: 'POST', json: {} })).rejects.toBeInstanceOf(
      ApiError,
    )

    expect(refreshCalls).toBe(0)
  })

  it('после неудачного обновления больше не дёргает /auth/refresh', async () => {
    let refreshCalls = 0
    server.use(
      http.post('/api/v1/auth/refresh', () => {
        refreshCalls += 1
        return unauthorized()
      }),
      http.get('/api/v1/me', () => unauthorized()),
    )

    await expect(apiFetch('/me')).rejects.toBeInstanceOf(ApiError)
    await expect(apiFetch('/me')).rejects.toBeInstanceOf(ApiError)

    expect(refreshCalls).toBe(1)
  })

  it('после успешного входа снова готов обновлять сессию', async () => {
    let refreshCalls = 0
    server.use(
      http.post('/api/v1/auth/refresh', () => {
        refreshCalls += 1
        return unauthorized()
      }),
      http.get('/api/v1/me', () => unauthorized()),
    )

    await expect(apiFetch('/me')).rejects.toBeInstanceOf(ApiError)
    markSessionActive()
    await expect(apiFetch('/me')).rejects.toBeInstanceOf(ApiError)

    expect(refreshCalls).toBe(2)
  })
})

describe('humanMessage', () => {
  it('переводит известный код в человеческий текст', () => {
    expect(humanMessage(new ApiError(401, 'invalid_credentials', 'x'))).toMatch(/неверн/i)
  })

  it('на 429 называет, сколько ждать', () => {
    const error = new ApiError(429, 'rate_limited', 'x', { retry_after: 42 })

    expect(humanMessage(error)).toContain('42')
  })

  it('на незнакомом коде отдаёт текст сервера', () => {
    expect(humanMessage(new ApiError(400, 'cycle_detected', 'Связь образует цикл'))).toBe(
      'Связь образует цикл',
    )
  })

  it('на сетевом сбое не показывает служебный текст исключения', () => {
    expect(humanMessage(new TypeError('Failed to fetch'))).toMatch(/сервер/i)
  })
})

describe('fieldErrors', () => {
  it('раскладывает 422 по именам полей', () => {
    const error = new ApiError(422, 'validation_error', 'x', {
      errors: [
        { loc: ['body', 'email'], msg: 'value is not a valid email address', type: 'value_error' },
        { loc: ['body', 'password'], msg: 'String should have at least 8 characters', type: 'x' },
      ],
    })

    expect(fieldErrors(error)).toEqual({
      email: 'value is not a valid email address',
      password: 'String should have at least 8 characters',
    })
  })

  it('на других ошибках не выдумывает полей', () => {
    expect(fieldErrors(new ApiError(409, 'email_already_registered', 'x'))).toEqual({})
  })
})

function unauthorized() {
  return HttpResponse.json(errorBody('unauthorized', 'Требуется аутентификация'), { status: 401 })
}

function delay(ms = 10) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
