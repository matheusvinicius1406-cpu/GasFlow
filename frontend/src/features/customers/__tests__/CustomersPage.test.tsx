import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

let customersState: {
  data: { items: unknown[]; total: number; total_pages: number } | null
  isLoading: boolean
  error: Error | null
  refetch: ReturnType<typeof vi.fn>
} = { data: { items: [], total: 0, total_pages: 0 }, isLoading: false, error: null, refetch: vi.fn() }

vi.mock('@/lib/api/hooks', () => ({
  useCustomers: () => customersState,
}))

import { CustomersPage } from '../CustomersPage'

const sampleCustomer = {
  codigo: 'CLT-001',
  nome: 'João da Silva',
  telefone: '11999990000',
  bairro: 'Centro',
  ativo: true,
}

describe('CustomersPage', () => {
  beforeEach(() => {
    customersState = { data: { items: [], total: 0, total_pages: 0 }, isLoading: false, error: null, refetch: vi.fn() }
  })

  it('shows loading spinner while loading', () => {
    customersState = { ...customersState, isLoading: true }
    const { container } = renderWithProviders(<CustomersPage />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders customers list', async () => {
    customersState = {
      ...customersState,
      data: { items: [sampleCustomer], total: 1, total_pages: 1 },
    }
    renderWithProviders(<CustomersPage />)
    await waitFor(() => {
      expect(screen.getByText('João da Silva')).toBeInTheDocument()
    })
  })

  it('shows empty state when no customers', () => {
    renderWithProviders(<CustomersPage />)
    expect(screen.getByText('Nenhum cliente cadastrado')).toBeInTheDocument()
  })

  it('shows error state on failure', () => {
    customersState = { ...customersState, error: new Error('boom') }
    renderWithProviders(<CustomersPage />)
    expect(screen.getByText('Não foi possível carregar os clientes.')).toBeInTheDocument()
  })
})
