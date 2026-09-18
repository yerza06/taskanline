/**
 * Единственная дверь в API.
 *
 * Здесь собрано всё, что иначе разъехалось бы по компонентам: cookie, заголовок
 * защиты от CSRF, разбор общего конверта ошибки и обновление протухшей сессии.
 * Компоненты про access-токен не знают вообще — и не должны.
 */

/** Все прикладные пути версионированы; `/health` живёт вне этого префикса. */
const API_PREFIX = '/api/v1'

export class ApiError extends Error {
  // Поля объявлены отдельно от конструктора: параметры-свойства TypeScript
  // не переживают стирание типов, а сборка требует только стираемый синтаксис.
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  /** Тело запроса; сериализуется и проставляет Content-Type. */
  json?: unknown
  signal?: AbortSignal
}

/**
 * Идёт ли уже обновление сессии.
 *
 * Общее на модуль, а не на запрос: три параллельных запроса, получившие 401
 * одновременно, должны разделить одно обновление. Иначе два из трёх предъявят
 * уже отозванный refresh-токен, бэкенд увидит повторное использование и погасит
 * все сессии пользователя.
 */
let refreshing: Promise<boolean> | null = null

/** Обновление уже проваливалось — повторять его до нового входа бессмысленно. */
let sessionLost = false

/** Вызывается после успешного входа, регистрации или обновления сессии. */
export function markSessionActive(): void {
  sessionLost = false
}

function send(path: string, options: RequestOptions): Promise<Response> {
  const { method = 'GET', json, signal } = options

  return fetch(`${API_PREFIX}${path}`, {
    method,
    signal,
    // Сессия живёт в httpOnly-cookie: без этого она просто не уедет.
    credentials: 'include',
    headers: {
      // Мутация с cookie и без этого заголовка получает 403 csrf_required.
      // Ставится на каждый запрос: дешевле, чем помнить, какие из них мутируют.
      'X-Requested-With': 'XMLHttpRequest',
      ...(json === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: json === undefined ? undefined : JSON.stringify(json),
  })
}

/** Путь самой аутентификации не рефрешится: получилась бы петля. */
function isAuthPath(path: string): boolean {
  return path.startsWith('/auth/')
}

function refreshSession(): Promise<boolean> {
  refreshing ??= send('/auth/refresh', { method: 'POST' })
    .then((response) => response.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null
    })

  return refreshing
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = `http_${response.status}`
  let message = 'Сервер ответил ошибкой'
  let details: Record<string, unknown> = {}

  try {
    const body: unknown = await response.json()
    const envelope = (body as { error?: Record<string, unknown> } | null)?.error
    if (envelope) {
      code = typeof envelope.code === 'string' ? envelope.code : code
      message = typeof envelope.message === 'string' ? envelope.message : message
      details = (envelope.details as Record<string, unknown> | undefined) ?? {}
    }
  } catch {
    // Тело не JSON — например, ответ прокси. Останутся статус и общий текст.
  }

  // 429 несёт срок ожидания и заголовком, и в details: берём то, что есть.
  if (details.retry_after === undefined) {
    const header = response.headers.get('Retry-After')
    if (header) {
      details = { ...details, retry_after: Number(header) }
    }
  }

  return new ApiError(response.status, code, message, details)
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options)

  if (response.status === 401 && !isAuthPath(path) && !sessionLost) {
    if (await refreshSession()) {
      response = await send(path, options)
    } else {
      sessionLost = true
    }
  }

  if (!response.ok) {
    throw await toApiError(response)
  }

  // 204 — законный ответ выхода и отзыва токена, тела у него нет.
  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
