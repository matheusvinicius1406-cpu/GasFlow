import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, renderWithRoute } from '@/test/utils'

const { customerState, createMock, updateMock } = vi.hoisted(() => ({
  customerState: { data: undefined as unknown, isLoading: false },
  createMock: vi.fn(),
  updateMock: vi.fn(),
}))

vi.mock('@/lib/api/hooks', () => ({
  useCustomer: () => customerState,
  useCreateCustomer: () => ({ mutateAsync: createMock, isPending: false }),
  useUpdateCustomer: () => ({ mutateAsync: updateMock, isPending: false }),
}))

import { CustomerFormPage } from '../CustomerFormPage'

function fillRequiredFields(value = 'valor-teste') {
  fireEvent.change(screen.getByPlaceholderText('Nome do cliente'), { target: { value } })
  // Telefone placeholder is duplicated (secondary phone); use label instead.
  fireEvent.change(screen.getByLabelText('Telefone *'), { target: { value } })
  fireEvent.change(screen.getByPlaceholderText('Nome da rua'), { target: { value } })
  fireEvent.change(screen.getByPlaceholderText('Número'), { target: { value } })
  fireEvent.change(screen.getByPlaceholderText('Bairro'), { target: { value } })
}

describe('CustomerFormPage', () => {
  beforeEach(() => {
    customerState.data = undefined
    customerState.isLoading = false
    createMock.mockReset().mockResolvedValue({ codigo: 'CLT-01' })
    updateMock.mockReset().mockResolvedValue({ codigo: 'CLT-01' })
  })

  it('renders new customer form', () => {
    renderWithProviders(<CustomerFormPage />, { route: '/customers/new' })
    expect(screen.getByText('Novo Cliente')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Nome do cliente')).toBeInTheDocument()
    expect(screen.getAllByPlaceholderText('(00) 00000-0000').length).toBeGreaterThanOrEqual(1)
  })

  it('creates customer on submit', async () => {
    renderWithProviders(<CustomerFormPage />, { route: '/customers/new' })
    fillRequiredFields()
    fireEvent.click(screen.getByRole('button', { name: /salvar/i }))
    await waitFor(() => {
      expect(createMock).toHaveBeenCalledTimes(1)
    })
    expect(createMock).toHaveBeenCalledWith(
      expect.objectContaining({ nome: 'valor-teste', telefone: 'valor-teste' })
    )
  })

  it('shows validation errors on empty submit', async () => {
    renderWithProviders(<CustomerFormPage />, { route: '/customers/new' })
    fireEvent.click(screen.getByRole('button', { name: /salvar/i }))
    await waitFor(() => {
      expect(screen.getByText('Nome é obrigatório')).toBeInTheDocument()
    })
    expect(createMock).not.toHaveBeenCalled()
  })

  it('renders edit form prefilled', async () => {
    Object.assign(customerState, {
      data: {
        codigo: 'CLT-01',
        nome: 'João da Silva',
        telefone: '11999990000',
        rua: 'Rua A',
        numero: '10',
        bairro: 'Centro',
        ativo: true,
        created_at: '2026-01-01',
        updated_at: '2026-01-01',
      },
      isLoading: false,
    })
    renderWithRoute(<CustomerFormPage />, '/customers/:codigo/edit', '/customers/CLT-01/edit')
    await waitFor(() => {
      expect(screen.getByText('Editar Cliente')).toBeInTheDocument()
      expect(screen.getByDisplayValue('João da Silva')).toBeInTheDocument()
    })
  })
})