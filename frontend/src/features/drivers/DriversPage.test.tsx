import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { DriversPage } from './DriversPage'

const { getMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  deleteMock: vi.fn(),
}))

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: getMock,
    delete: deleteMock,
  },
}))

const DRIVER = {
  codigo: '600001',
  nome: 'João Motorista',
  telefone: '11999990000',
  placa: 'ABC-1234',
  ativo: true,
  status: 'AVAILABLE',
}

function withDriver() {
  getMock.mockImplementation((url: string) => {
    if (url === '/delivery-drivers/') return Promise.resolve({ data: [DRIVER] })
    return Promise.resolve({ data: { locations: [] } })
  })
}

describe('DriversPage', () => {
  beforeEach(() => {
    getMock.mockReset().mockResolvedValue({ data: [] })
    deleteMock.mockReset().mockResolvedValue({ data: { success: true } })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows empty state when no drivers', async () => {
    renderWithProviders(<DriversPage />)
    await waitFor(() => {
      expect(screen.getByText(/Nenhum motorista/i)).toBeInTheDocument()
    })
  })

  it('renders without crashing', async () => {
    const { container } = renderWithProviders(<DriversPage />)
    await waitFor(() => {
      expect(container.firstChild).toBeTruthy()
    })
  })

  it('asks for confirmation naming the driver', async () => {
    withDriver()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)

    renderWithProviders(<DriversPage />)
    const botao = await screen.findByRole('button', { name: 'Excluir João Motorista' })
    fireEvent.click(botao)

    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(String(confirmSpy.mock.calls[0]?.[0])).toContain('João Motorista')
    // cancelou: nada é chamado e o motorista continua na tela
    expect(deleteMock).not.toHaveBeenCalled()
    expect(screen.getByText('João Motorista')).toBeInTheDocument()
  })

  it('exclui no endpoint único e recarrega a lista', async () => {
    withDriver()
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderWithProviders(<DriversPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Excluir João Motorista' }))

    await waitFor(() => {
      expect(deleteMock).toHaveBeenCalledWith('/admin/drivers/600001')
    })
    await waitFor(() => {
      expect(screen.getByText(/João Motorista foi excluído/i)).toBeInTheDocument()
    })
    // a lista é recarregada depois da exclusão
    expect(getMock.mock.calls.filter(([url]) => url === '/delivery-drivers/').length).toBeGreaterThan(1)
  })

  it('explica o 409 de entrega em rota', async () => {
    withDriver()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    deleteMock.mockRejectedValue({ response: { status: 409 } })

    renderWithProviders(<DriversPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Excluir João Motorista' }))

    await waitFor(() => {
      expect(screen.getByText(/entrega em rota/i)).toBeInTheDocument()
    })
  })
})
