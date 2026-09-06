import { screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { IntelligencePage } from './IntelligencePage'

describe('IntelligencePage', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('renders the Copilot assistant', () => {
    renderWithProviders(<IntelligencePage />)
    expect(screen.getByText('Copilot')).toBeInTheDocument()
    expect(screen.getByText('Olá! Sou o assistente do GasFlow.')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Digite sua pergunta...')).toBeInTheDocument()
  })
})
