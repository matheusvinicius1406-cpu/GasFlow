import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

let getMock = vi.fn<(url: string) => Promise<{ data: unknown }>>()

vi.mock('@/lib/api/client', () => ({
  apiClient: { get: (url: string) => getMock(url) },
}))

import { ReportsPage } from '../ReportsPage'

describe('ReportsPage', () => {
  beforeEach(() => {
    getMock = vi.fn((url: string) => {
      if (url === '/finance/cash/balance') {
        return Promise.resolve({ data: { balance: 500 } })
      }
      return Promise.resolve({
        data: {
          date: '2026-09-04',
          total_receipts: 2500,
          total_expenses: 300,
        },
      })
    })
  })

  it('shows loading spinner while loading', () => {
    getMock = vi.fn(() => new Promise(() => {}))
    const { container } = renderWithProviders(<ReportsPage />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders daily report with summary', async () => {
    renderWithProviders(<ReportsPage />)
    await waitFor(() => {
      expect(screen.getByText('Relatório Diário — 2026-09-04')).toBeInTheDocument()
    })
    expect(screen.getByText('Saldo em Caixa')).toBeInTheDocument()
    expect(screen.getByText('Recebimentos Hoje')).toBeInTheDocument()
    expect(screen.getByText('Despesas Hoje')).toBeInTheDocument()
  })

  it('shows error state on failure', async () => {
    getMock = vi.fn(() => Promise.reject(new Error('boom')))
    renderWithProviders(<ReportsPage />)
    await waitFor(() => {
      expect(screen.getByText('Não foi possível carregar os relatórios.')).toBeInTheDocument()
    })
  })
})