import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, renderWithRoute } from '@/test/utils'

const { getMock, postMock, putMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  putMock: vi.fn(),
}))

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: getMock,
    post: postMock,
    put: putMock,
  },
}))

import { DriverFormPage } from '../DriverFormPage'

describe('DriverFormPage', () => {
  beforeEach(() => {
    getMock.mockReset().mockResolvedValue({ data: {} })
    postMock.mockReset().mockResolvedValue({ data: {} })
    putMock.mockReset().mockResolvedValue({ data: {} })
  })

  it('renders new driver form', () => {
    renderWithProviders(<DriverFormPage />, { route: '/drivers/new' })
    expect(screen.getByText('Novo Motorista')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Nome do motorista')).toBeInTheDocument()
  })

  it('creates driver on submit', async () => {
    renderWithProviders(<DriverFormPage />, { route: '/drivers/new' })
    fireEvent.change(screen.getByPlaceholderText('Nome do motorista'), {
      target: { value: 'João Motorista' },
    })
    fireEvent.change(screen.getByPlaceholderText('(00) 00000-0000'), {
      target: { value: '11999990000' },
    })
    fireEvent.click(screen.getByRole('button', { name: /salvar/i }))
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledTimes(1)
    })
    expect(postMock).toHaveBeenCalledWith(
      '/delivery-drivers/',
      expect.objectContaining({ nome: 'João Motorista', telefone: '11999990000' })
    )
  })

  it('shows error when required fields missing', async () => {
    renderWithProviders(<DriverFormPage />, { route: '/drivers/new' })
    // Inputs have the HTML `required` attribute, so jsdom blocks the submit
    // event for empty values. Whitespace-only values pass `required` but fail
    // the trim() validation inside handleSubmit — the real error path.
    fireEvent.change(screen.getByPlaceholderText('Nome do motorista'), {
      target: { value: '   ' },
    })
    fireEvent.change(screen.getByPlaceholderText('(00) 00000-0000'), {
      target: { value: '   ' },
    })
    fireEvent.click(screen.getByRole('button', { name: /salvar/i }))
    await waitFor(() => {
      expect(screen.getByText('Nome e telefone são obrigatórios')).toBeInTheDocument()
    })
    expect(postMock).not.toHaveBeenCalled()
  })

  it('renders edit form prefilled and updates on submit', async () => {
    getMock.mockResolvedValue({
      data: { nome: 'João Motorista', telefone: '11999990000', placa: 'ABC-1234', vehicle_type: 'CAR' },
    })
    renderWithRoute(<DriverFormPage />, '/drivers/:codigo/edit', '/drivers/M1/edit')
    await waitFor(() => {
      expect(screen.getByText('Editar Motorista')).toBeInTheDocument()
      expect(screen.getByDisplayValue('João Motorista')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: /salvar/i }))
    await waitFor(() => {
      expect(putMock).toHaveBeenCalledWith(
        '/delivery-drivers/M1',
        expect.objectContaining({ nome: 'João Motorista' })
      )
    })
  })
})