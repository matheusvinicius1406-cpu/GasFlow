import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

let inventoryState: {
  data: { items: unknown[]; total: number } | null
  isLoading: boolean
  error: Error | null
  refetch: ReturnType<typeof vi.fn>
} = { data: { items: [], total: 0 }, isLoading: false, error: null, refetch: vi.fn() }
let productsState: unknown[] = []

vi.mock('@/lib/api/hooks', () => ({
  useInventoryList: () => inventoryState,
  useProducts: () => ({ data: productsState }),
}))

import { InventoryPage } from '../InventoryPage'

const sampleItem = {
  product_codigo: 'PROD-1',
  quantity: 10,
  available_quantity: 10,
  minimum_quantity: 5,
  stock_status: 'OK',
}
const sampleProduct = { codigo: 'PROD-1', nome: 'Gás P13', tipo: 'GAS', preco: 120.0 }

describe('InventoryPage', () => {
  beforeEach(() => {
    inventoryState = { data: { items: [], total: 0 }, isLoading: false, error: null, refetch: vi.fn() }
    productsState = []
  })

  it('shows loading spinner while loading', () => {
    inventoryState = { ...inventoryState, isLoading: true }
    const { container } = renderWithProviders(<InventoryPage />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders inventory items', async () => {
    inventoryState = { ...inventoryState, data: { items: [sampleItem], total: 1 } }
    productsState = [sampleProduct]
    renderWithProviders(<InventoryPage />)
    await waitFor(() => {
      expect(screen.getByText('Gás P13')).toBeInTheDocument()
    })
  })

  it('shows empty state when no inventory', () => {
    renderWithProviders(<InventoryPage />)
    expect(screen.getByText('Nenhum produto no inventário')).toBeInTheDocument()
  })

  it('shows error state on failure', () => {
    inventoryState = { ...inventoryState, error: new Error('boom') }
    renderWithProviders(<InventoryPage />)
    expect(screen.getByText('Não foi possível carregar o inventário.')).toBeInTheDocument()
  })
})
