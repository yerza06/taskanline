const DATE_TIME = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** Дата и время из ISO-строки бэкенда. */
export function formatDateTime(value: string): string {
  return DATE_TIME.format(new Date(value))
}
