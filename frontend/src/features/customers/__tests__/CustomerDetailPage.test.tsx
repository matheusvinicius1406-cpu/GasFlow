import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithRoute } from '@/test/utils'

const { customerState, ordersState, disableMock } = vi.hoisted(() => ({
  customerState: { data: undefined as unknown, isLoading: false, error: null as Error | null, refetch: vi.fn() },
  ordersState: { data: [] as unknown[] },
  disableMock: vi.fn(),
}))

vi.mock('@/lib/api/hooks', () => ({
  useCustomer360: () => customerState,
  useCustomerOrders: () => ordersState,
  useDisableCustomer: () => ({ mutateAsync: disableMock, isPending: false }),
}))

// A ficha inclui o card LGPD (useAuth/useToast); o harness de rota não tem
// esses providers — sem permissão o card não renderiza, que é o caso aqui.
vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => false }),
}))
vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))

import { CustomerDetailPage } from '../CustomerDetailPage'

const customer = {
  codigo: 'CLT-1',
  nome: 'João da Silva',
  telefone: '11999990000',
  ativo: true,
  tipo: 'CONSUMER',
  rua: 'Rua A',
  numero: '10',
  bairro: 'Centro',
  created_at: '2026-09-01T10:00:00',
  updated_at: '2026-09-02T10:00:00',
  total_orders: 3,
  total_spent: 300,
  average_ticket: 100,
  days_since_last_order: 5,
  favorite_product: 'Gás P13',
}

function render() {
  return renderWithRoute(<CustomerDetailPage />, '/customers/:codigo', '/customers/CLT-1')
}

describe('CustomerDetailPage', () => {
  beforeEach(() => {
    customerState.data = undefined
    customerState.isLoading = false
    customerState.error = null
    ordersState.data = []
    disableMock.mockReset().mockResolvedValue(undefined)
  })

  it('shows loading spinner while loading', () => {
    customerState.isLoading = true
    const { container } = render()
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders the customer header and contact info', async () => {
    customerState.data = customer
    render()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'João da Silva' })).toBeInTheDocument()
    })
    expect(screen.getByText('Código: CLT-1')).toBeInTheDocument()
    expect(screen.getByText('Ativo')).toBeInTheDocument()
  })

  it('renders the CRM metrics and favorite product when there are orders', async () => {
    customerState.data = customer
    render()
    await waitFor(() => {
      expect(screen.getByText('Total de Pedidos')).toBeInTheDocument()
    })
    expect(screen.getByText('Produto Favorito')).toBeInTheDocument()
    expect(screen.getByText('Gás P13')).toBeInTheDocument()
  })

  it('hides the metrics block for a customer without orders', async () => {
    customerState.data = { ...customer, total_orders: 0, favorite_product: null }
    render()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'João da Silva' })).toBeInTheDocument()
    })
    expect(screen.queryByText('Total de Pedidos')).not.toBeInTheDocument()
  })

  it('shows the error state when the customer cannot be loaded', () => {
    customerState.error = new Error('boom')
    render()
    expect(
      screen.getByText('Não foi possível carregar os dados do cliente.')
    ).toBeInTheDocument()
  })
})
