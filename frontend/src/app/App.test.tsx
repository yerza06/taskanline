import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { App } from './App'

describe('App', () => {
  it('рендерит оболочку приложения с шапкой, навигацией и областью контента', () => {
    render(<App />)

    expect(screen.getByRole('banner')).toHaveTextContent('TasKanLine')
    expect(screen.getByRole('navigation')).toBeInTheDocument()
    expect(screen.getByRole('main')).toBeInTheDocument()
  })
})
