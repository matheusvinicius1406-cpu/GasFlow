import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

const { customersState, productsState, createOrderMock, clientGetMock } = vi.hoisted(() => ({
  customersState: { data: [] as unknown[], isLoading: false },
  productsState: { data: [] as unknown[], isLoading: false },
  createOrderMock: vi.fn(),
  clientGetMock: vi.fn(),
}))

vi.mock('@/lib/api/hooks', () => ({
  useCustomersLegacy: () => customersState,
  useProducts: () => productsState,
  useCreateOrder: () => ({ mutateAsync: createOrderMock, isPending: false }),
}))

vi.mock('@/lib/api/client', () => ({
  apiClient: { get: clientGetMock },
}))

import { OrderFormPage } from '../OrderFormPage'

function resetState() {
  customersState.data = []
  customersState.isLoading = false
  productsState.data = []
  productsState.isLoading = false
  createOrderMock.mockReset().mockResolvedValue({ codigo: 'ORD-1' })
  clientGetMock.mockReset().mockResolvedValue({ data: { methods: [] } })
}

describe('OrderFormPage', () => {
  beforeEach(() => {
    resetState()
  })

  it('shows loading spinner while loading', () => {
    productsState.isLoading = true
    const { container } = renderWithProviders(<OrderFormPage />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders new order form with customer and product selectors', async () => {
    customersState.data = [
      { codigo: 'CLT-1', nome: 'João da Silva', telefone: '11999990000', bairro: 'Centro', ativo: true, created_at: '', updated_at: '' },
    ]
    productsState.data = [
      { codigo: 'PROD-1', nome: 'Gás P13', tipo: 'GAS', preco: 120, estoque: 5, ativo: true },
    ]
    renderWithProviders(<OrderFormPage />)
    await waitFor(() => {
      expect(screen.getByText('Novo Pedido')).toBeInTheDocument()
    })
    expect(screen.getByText('CLT-1 - João da Silva (Centro)')).toBeInTheDocument()
    expect(clientGetMock).toHaveBeenCalledWith('/payments/methods')
  })
})