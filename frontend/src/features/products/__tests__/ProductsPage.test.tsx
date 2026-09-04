import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

let productsState: {
  data: unknown[] | null
  isLoading: boolean
  error: Error | null
  refetch: ReturnType<typeof vi.fn>
} = { data: [], isLoading: false, error: null, refetch: vi.fn() }

vi.mock('@/lib/api/hooks', () => ({
  useProducts: () => productsState,
}))

import { ProductsPage } from '../ProductsPage'

const sampleProduct = {
  codigo: 'PROD-1',
  nome: 'Gás P13',
  tipo: 'GAS',
  preco: 120.0,
  estoque: 5,
}

describe('ProductsPage', () => {
  beforeEach(() => {
    productsState = { data: [], isLoading: false, error: null, refetch: vi.fn() }
  })

  it('shows loading spinner while loading', () => {
    productsState = { ...productsState, isLoading: true }
    const { container } = renderWithProviders(<ProductsPage />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders products list', async () => {
    productsState = { ...productsState, data: [sampleProduct] }
    renderWithProviders(<ProductsPage />)
    await waitFor(() => {
      expect(screen.getByText('Gás P13')).toBeInTheDocument()
    })
    expect(screen.getByText('R$ 120,00')).toBeInTheDocument()
  })

  it('shows empty state when no products', () => {
    renderWithProviders(<ProductsPage />)
    expect(screen.getByText('Nenhum produto cadastrado')).toBeInTheDocument()
  })

  it('shows error state on failure', () => {
    productsState = { ...productsState, error: new Error('boom') }
    renderWithProviders(<ProductsPage />)
    expect(screen.getByText('Não foi possível carregar os produtos.')).toBeInTheDocument()
  })
})