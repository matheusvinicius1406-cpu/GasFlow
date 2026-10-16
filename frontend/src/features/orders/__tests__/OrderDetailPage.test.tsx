import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithRoute } from '@/test/utils'

const { orderState, statusMock, registerPaymentMock, receivablesState, paymentsState } = vi.hoisted(() => ({
  orderState: { data: undefined as unknown, isLoading: false, error: null as Error | null, refetch: vi.fn() },
  statusMock: vi.fn(),
  registerPaymentMock: vi.fn(),
  receivablesState: { data: { items: [] as unknown[] } },
  paymentsState: { data: { items: [] as unknown[] } },
}))

vi.mock('@/lib/api/hooks', () => ({
  useOrder: () => orderState,
  useUpdateOrderStatus: () => ({ mutateAsync: statusMock, isPending: false }),
  useRegisterPayment: () => ({ mutateAsync: registerPaymentMock, isPending: false }),
  useReceivables: () => receivablesState,
  useOrderPayments: () => paymentsState,
}))

import { OrderDetailPage } from '../OrderDetailPage'

const order = {
  codigo: 'ORD-1',
  client_codigo: 'CLT-1',
  status: 'PENDING',
  payment_status: 'PENDING',
  total: 150.5,
  subtotal: 140.5,
  delivery_fee: 10,
  discount: 0,
  address_snapshot: 'Rua A, 10 - Centro',
  created_at: '2026-09-01T10:00:00',
  items: [{ id: 'i1', product_nome: 'Gás P13', quantity: 1, unit_price: 140.5, subtotal: 140.5 }],
}

function render() {
  return renderWithRoute(<OrderDetailPage />, '/orders/:codigo', '/orders/ORD-1')
}

describe('OrderDetailPage', () => {
  beforeEach(() => {
    orderState.data = undefined
    orderState.isLoading = false
    orderState.error = null
    receivablesState.data = { items: [] }
    paymentsState.data = { items: [] }
    statusMock.mockReset().mockResolvedValue(undefined)
    registerPaymentMock.mockReset().mockResolvedValue(undefined)
  })

  it('shows loading spinner while loading', () => {
    orderState.isLoading = true
    const { container } = render()
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders the order header, items and totals', async () => {
    orderState.data = order
    render()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Pedido #ORD-1' })).toBeInTheDocument()
    })
    expect(screen.getByText('Código: CLT-1')).toBeInTheDocument()
    expect(screen.getByText('Gás P13')).toBeInTheDocument()
    expect(screen.getByText('Rua A, 10 - Centro')).toBeInTheDocument()
  })

  it('offers the status transitions for a PENDING order', async () => {
    orderState.data = order
    render()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Confirmar' })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeInTheDocument()
  })

  it('opens the payment form when registering a payment', async () => {
    orderState.data = order
    render()
    fireEvent.click(await screen.findByRole('button', { name: /Registrar Pagamento/i }))
    expect(screen.getByLabelText(/Valor \(R\$\)/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar Pagamento' })).toBeInTheDocument()
  })

  it('shows the error state when the order cannot be loaded', () => {
    orderState.error = new Error('boom')
    render()
    expect(
      screen.getByText('Não foi possível carregar os dados do pedido.')
    ).toBeInTheDocument()
  })
})
