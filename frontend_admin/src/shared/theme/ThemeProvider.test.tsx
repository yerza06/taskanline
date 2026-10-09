import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { mockPrefersColorScheme } from '../../test/setup'
import { THEME_STORAGE_KEY } from './theme'
import { ThemeProvider } from './ThemeProvider'
import { ThemeToggle } from './ThemeToggle'

function renderWithProvider() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  )
}

const isDark = () => document.documentElement.classList.contains('dark')

describe('ThemeProvider', () => {
  it('при системной тёмной теме сразу включает тёмное оформление', () => {
    mockPrefersColorScheme(true)

    renderWithProvider()

    expect(isDark()).toBe(true)
  })

  it('следит за сменой системной темы, пока пользователь не выбрал своё', () => {
    const media = mockPrefersColorScheme(false)
    renderWithProvider()
    expect(isDark()).toBe(false)

    act(() => media.emit(true))

    expect(isDark()).toBe(true)
  })

  it('выбор пользователя переживает перемонтирование', () => {
    mockPrefersColorScheme(false)
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')

    renderWithProvider()

    expect(isDark()).toBe(true)
  })
})

describe('ThemeToggle', () => {
  it('переключает тему и сохраняет выбор', async () => {
    mockPrefersColorScheme(false)
    const user = userEvent.setup()
    renderWithProvider()

    await user.click(screen.getByRole('button', { name: /тема/i }))

    expect(isDark()).toBe(true)
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')

    await user.click(screen.getByRole('button', { name: /тема/i }))

    expect(isDark()).toBe(false)
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
  })

  it('сообщает текущую тему в доступном имени кнопки', () => {
    mockPrefersColorScheme(false)

    renderWithProvider()

    expect(screen.getByRole('button', { name: /светлая тема/i })).toBeInTheDocument()
  })
})
