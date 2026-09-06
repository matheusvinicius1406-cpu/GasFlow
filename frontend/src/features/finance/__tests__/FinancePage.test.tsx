import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

let getMock = vi.fn<(url: string) => Promise<{ data: unknown }>>()
let receivablesState: unknown = { items: [], total: 0, total_pages: 1 }
let cashBalanceState: unknown = { balance: 0 }

vi.mock('@/lib/api/client', () => ({
  apiClient: { get: (url: string) => getMock(url) },
}))

vi.mock('@/lib/api/hooks', () => ({
  useReceivables: () => ({ data: receivablesState, isLoading: false }),
  useCashBalance: () => ({ data: cashBalanceState }),
}))

import { FinancePage } from '../FinancePage'

describe('FinancePage', () => {
  beforeEach(() => {
    getMock = vi.fn((url: string) => {
      if (url === '/finance/cash/balance') {
        return Promise.resolve({ data: { balance: 1234.5 } })
      }
      return Promise.resolve({ data: { items: [] } })
    })
    receivablesState = { items: [], total: 0, total_pages: 1 }
    cashBalanceState = { balance: 0 }
  })

  it('shows loading spinner while loading', () => {
    getMock = vi.fn(() => new Promise(() => {}))
    const { container } = renderWithProviders(<FinancePage />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders summary cards with data', async () => {
    renderWithProviders(<FinancePage />)
    await waitFor(() => {
      expect(screen.getByText('Financeiro')).toBeInTheDocument()
    })
    expect(screen.getByText('Saldo em Caixa')).toBeInTheDocument()
    expect(screen.getByText('R$ 1234,50')).toBeInTheDocument()
    expect(screen.getByText('Total Recebido')).toBeInTheDocument()
    expect(screen.getByText('Total Despesas')).toBeInTheDocument()
    expect(screen.getByText('💳 Pagamentos')).toBeInTheDocument()
    expect(screen.getByText('📄 Recebíveis')).toBeInTheDocument()
  })

  it('shows error state on failure', async () => {
    getMock = vi.fn(() => Promise.reject(new Error('boom')))
    renderWithProviders(<FinancePage />)
    await waitFor(() => {
      expect(screen.getByText('Não foi possível carregar os dados financeiros.')).toBeInTheDocument()
    })
  })
})
