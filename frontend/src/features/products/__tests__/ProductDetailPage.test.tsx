import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithRoute } from '@/test/utils'

const { productState, inventoryState, disableMock } = vi.hoisted(() => ({
  productState: { data: undefined as unknown, isLoading: false, error: null as Error | null, refetch: vi.fn() },
  inventoryState: { data: undefined as unknown },
  disableMock: vi.fn(),
}))

vi.mock('@/lib/api/hooks', () => ({
  useProduct: () => productState,
  useInventoryItem: () => inventoryState,
  useDisableProduct: () => ({ mutateAsync: disableMock, isPending: false }),
}))

import { ProductDetailPage } from '../ProductDetailPage'

const baseProduct = {
  codigo: 'PROD-1',
  nome: 'Gás P13',
  tipo: 'GAS',
  preco: 120,
  estoque: 5,
  ativo: true,
  created_at: '2026-09-01T10:00:00',
  updated_at: '2026-09-02T10:00:00',
}

function render() {
  return renderWithRoute(<ProductDetailPage />, '/products/:codigo', '/products/PROD-1')
}

describe('ProductDetailPage', () => {
  beforeEach(() => {
    productState.data = undefined
    productState.isLoading = false
    productState.error = null
    inventoryState.data = undefined
    disableMock.mockReset().mockResolvedValue(undefined)
  })

  it('shows loading spinner while loading', () => {
    productState.isLoading = true
    const { container } = render()
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders the product details', async () => {
    productState.data = baseProduct
    render()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Gás P13' })).toBeInTheDocument()
    })
    expect(screen.getByText('Código: PROD-1')).toBeInTheDocument()
    expect(screen.getByText('R$ 120,00')).toBeInTheDocument()
    expect(screen.getByText('Ativo')).toBeInTheDocument()
  })

  it('falls back to product stock when inventory is absent', async () => {
    productState.data = baseProduct
    render()
    await waitFor(() => {
      expect(screen.getByText('unidades em estoque')).toBeInTheDocument()
    })
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('warns when inventory is at or below the minimum', async () => {
    productState.data = baseProduct
    inventoryState.data = { quantity: 2, minimum_quantity: 5 }
    render()
    await waitFor(() => {
      expect(screen.getByText(/Estoque baixo! Mínimo: 5\./)).toBeInTheDocument()
    })
  })

  it('shows the error state when the product cannot be loaded', () => {
    productState.error = new Error('boom')
    render()
    expect(
      screen.getByText('Não foi possível carregar os dados do produto.')
    ).toBeInTheDocument()
  })
})
