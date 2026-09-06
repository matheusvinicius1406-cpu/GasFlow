import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

let ordersState: {
  data: unknown[] | null
  isLoading: boolean
  error: Error | null
  refetch: ReturnType<typeof vi.fn>
} = { data: [], isLoading: false, error: null, refetch: vi.fn() }

vi.mock('@/lib/api/hooks', () => ({
  useOrders: () => ordersState,
}))

import { OrdersPage } from '../OrdersPage'

const sampleOrder = {
  codigo: 'ORD-001',
  client_codigo: 'CLT-001',
  status: 'PENDING',
  source: 'MANUAL',
  payment_status: 'PENDING',
  total: 150.5,
  address_snapshot: 'Rua A, 10 - Centro',
  created_at: '2026-09-01T10:00:00',
}

describe('OrdersPage', () => {
  beforeEach(() => {
    ordersState = { data: [], isLoading: false, error: null, refetch: vi.fn() }
  })

  it('shows loading spinner while loading', () => {
    ordersState = { ...ordersState, isLoading: true }
    const { container } = renderWithProviders(<OrdersPage />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders orders list', async () => {
    ordersState = { ...ordersState, data: [sampleOrder] }
    renderWithProviders(<OrdersPage />)
    await waitFor(() => {
      expect(screen.getByText('#ORD-001')).toBeInTheDocument()
    })
    expect(screen.getByText('R$ 150,50')).toBeInTheDocument()
    expect(screen.getByText(/CLT-001/)).toBeInTheDocument()
  })

  it('shows empty state when no orders', () => {
    renderWithProviders(<OrdersPage />)
    expect(screen.getByText('Nenhum pedido')).toBeInTheDocument()
  })

  it('shows error state on failure', () => {
    ordersState = { ...ordersState, error: new Error('boom') }
    renderWithProviders(<OrdersPage />)
    expect(screen.getByText('Não foi possível carregar os pedidos.')).toBeInTheDocument()
  })
})
