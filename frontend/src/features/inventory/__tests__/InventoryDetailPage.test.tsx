import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithRoute } from '@/test/utils'

const { inventoryState, movementsState, productsState, mutationMock } = vi.hoisted(() => {
  const inventoryState = { data: undefined as unknown, isLoading: false, error: null as Error | null, refetch: vi.fn() }
  const movementsState = { data: undefined as unknown, isLoading: false }
  const productsState = { data: [] as unknown[] }
  const mutationMock = vi.fn()
  return { inventoryState, movementsState, productsState, mutationMock }
})

vi.mock('@/lib/api/hooks', () => ({
  useInventoryItem: () => inventoryState,
  useInventoryMovements: () => movementsState,
  useProducts: () => productsState,
  useAddStock: () => ({ mutateAsync: mutationMock, isPending: false }),
  useAdjustStock: () => ({ mutateAsync: mutationMock, isPending: false }),
  useRecordLoss: () => ({ mutateAsync: mutationMock, isPending: false }),
}))

import { InventoryDetailPage } from '../InventoryDetailPage'

const inventory = {
  product_codigo: 'PROD-1',
  quantity: 10,
  minimum_quantity: 2,
  stock_status: 'IN_STOCK',
}

function render() {
  return renderWithRoute(
    <InventoryDetailPage />,
    '/inventory/:productCodigo',
    '/inventory/PROD-1'
  )
}

describe('InventoryDetailPage', () => {
  beforeEach(() => {
    inventoryState.data = undefined
    inventoryState.isLoading = false
    inventoryState.error = null
    movementsState.data = { items: [], total: 0, total_pages: 1 }
    movementsState.isLoading = false
    productsState.data = []
    mutationMock.mockReset().mockResolvedValue(undefined)
  })

  it('shows loading spinner while loading', () => {
    inventoryState.isLoading = true
    const { container } = render()
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders stock stats and the product code', async () => {
    inventoryState.data = inventory
    render()
    await waitFor(() => {
      expect(screen.getByText('Código: PROD-1')).toBeInTheDocument()
    })
    // "Em Estoque" aparece no badge de status e no StatCard de status.
    expect(screen.getAllByText('Em Estoque').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Total Movimentações')).toBeInTheDocument()
  })

  it('uses the product name when the product list has it', async () => {
    inventoryState.data = inventory
    productsState.data = [
      { codigo: 'PROD-1', nome: 'Gás P13', tipo: 'GAS', preco: 120, ativo: true },
    ]
    render()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Gás P13' })).toBeInTheDocument()
    })
  })

  it('shows the empty state when there are no movements', async () => {
    inventoryState.data = inventory
    render()
    await waitFor(() => {
      expect(screen.getByText('Nenhuma movimentação')).toBeInTheDocument()
    })
  })

  it('shows the error state when inventory cannot be loaded', () => {
    inventoryState.error = new Error('boom')
    render()
    expect(
      screen.getByText('Não foi possível carregar os dados de inventário.')
    ).toBeInTheDocument()
  })
})
