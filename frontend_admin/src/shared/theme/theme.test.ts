import { beforeEach, describe, expect, it, vi } from 'vitest'

import { mockPrefersColorScheme } from '../../test/setup'
import {
  THEME_STORAGE_KEY,
  applyTheme,
  readStoredPreference,
  resolveTheme,
  storePreference,
} from './theme'

describe('readStoredPreference', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('без сохранённого значения возвращает system', () => {
    expect(readStoredPreference()).toBe('system')
  })

  it('читает сохранённое значение', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')

    expect(readStoredPreference()).toBe('dark')
  })

  it('игнорирует мусор в хранилище', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'нечто')

    expect(readStoredPreference()).toBe('system')
  })
})

describe('resolveTheme', () => {
  it('явный выбор пользователя важнее системного', () => {
    mockPrefersColorScheme(true)

    expect(resolveTheme('light')).toBe('light')
  })

  it('при system берёт системную тему', () => {
    mockPrefersColorScheme(true)

    expect(resolveTheme('system')).toBe('dark')
  })
})

describe('applyTheme', () => {
  it('вешает класс dark на корневой элемент и снимает его', () => {
    applyTheme('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    applyTheme('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})

describe('storePreference', () => {
  it('сохраняет выбор пользователя', () => {
    storePreference('dark')

    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
  })

  it('не падает, когда localStorage недоступен', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('приватный режим')
    })

    expect(() => storePreference('dark')).not.toThrow()

    setItem.mockRestore()
  })
})
