import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, renderWithRoute } from '@/test/utils'

let productState: { data: unknown; isLoading: boolean } = { data: undefined, isLoading: false }
const createMock = vi.fn()
const updateMock = vi.fn()

vi.mock('@/lib/api/hooks', () => ({
  useProduct: () => productState,
  useCreateProduct: () => ({ mutateAsync: createMock, isPending: false }),
  useUpdateProduct: () => ({ mutateAsync: updateMock, isPending: false }),
}))

import { ProductFormPage } from '../ProductFormPage'

describe('ProductFormPage', () => {
  beforeEach(() => {
    productState = { data: undefined, isLoading: false }
    createMock.mockReset().mockResolvedValue({ codigo: 'PROD-1' })
    updateMock.mockReset().mockResolvedValue({ codigo: 'PROD-1' })
  })

  it('renders new product form', () => {
    renderWithProviders(<ProductFormPage />, { route: '/products/new' })
    expect(screen.getByText('Novo Produto')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Ex: Gás P13, Água 20L')).toBeInTheDocument()
  })

  it('creates product on submit', async () => {
    renderWithProviders(<ProductFormPage />, { route: '/products/new' })
    fireEvent.change(screen.getByPlaceholderText('Ex: Gás P13, Água 20L'), {
      target: { value: 'Gás P13' },
    })
    fireEvent.change(screen.getByLabelText(/tipo/i), { target: { value: 'GAS' } })
    fireEvent.change(screen.getByPlaceholderText('0.00'), { target: { value: '120.5' } })
    fireEvent.click(screen.getByRole('button', { name: /salvar/i }))
    await waitFor(() => {
      expect(createMock).toHaveBeenCalledTimes(1)
    })
    expect(createMock).toHaveBeenCalledWith(
      expect.objectContaining({ nome: 'Gás P13', tipo: 'GAS', preco: 120.5 })
    )
  })

  it('shows validation errors on empty submit', async () => {
    renderWithProviders(<ProductFormPage />, { route: '/products/new' })
    fireEvent.click(screen.getByRole('button', { name: /salvar/i }))
    await waitFor(() => {
      expect(screen.getByText('Nome é obrigatório')).toBeInTheDocument()
    })
    expect(createMock).not.toHaveBeenCalled()
  })

  it('renders edit form prefilled', async () => {
    productState = {
      data: {
        codigo: 'PROD-1',
        nome: 'Água 20L',
        tipo: 'AGUA',
        preco: 15,
        estoque: 20,
        ativo: true,
        created_at: '2026-01-01',
        updated_at: '2026-01-01',
      },
      isLoading: false,
    }
    renderWithRoute(<ProductFormPage />, '/products/:codigo/edit', '/products/PROD-1/edit')
    await waitFor(() => {
      expect(screen.getByText('Editar Produto')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Água 20L')).toBeInTheDocument()
    })
  })
})