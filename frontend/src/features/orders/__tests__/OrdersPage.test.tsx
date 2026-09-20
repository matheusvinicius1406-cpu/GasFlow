import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

let ordersState: {
  data: unknown[] | null
  isLoading: boolean
  error: Error | null
  refetch: ReturnType<typeof vi.fn>
} = { data: [], isLoading: false, error: null, refetch: vi.fn() }

vi.mock('@/lib/api/hooks', () => ({
  useOrders: () => ordersState,
}))

const apiPost = vi.fn().mockResolvedValue({ data: { success: true } })
const apiGet = vi.fn()
vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
  },
}))

/** Status da impressora respondido pelo backend (`/printer/status`). */
const statusComImpressora = {
  status: 'ONLINE',
  printer_name: 'GT710',
  stale: false,
  pending_jobs: 0,
  failed_jobs: 0,
}

import { OrdersPage } from '../OrdersPage'

const sampleOrder = {
  codigo: 'ORD-001',
  client_codigo: 'CLT-001',
  status: 'PENDING',
  source: 'MANUAL',
  payment_status: 'PENDING',
  total: 150.5,
  address_snapshot: 'Rua A, 10 - Centro',
  created_at: '2026-09-01T10:00:00',
}

describe('OrdersPage', () => {
  beforeEach(() => {
    ordersState = { data: [], isLoading: false, error: null, refetch: vi.fn() }
    apiPost.mockClear()
    apiPost.mockResolvedValue({ data: { success: true } })
    apiGet.mockReset()
    apiGet.mockResolvedValue({ data: statusComImpressora })
  })

  it('shows loading spinner while loading', () => {
    ordersState = { ...ordersState, isLoading: true }
    const { container } = renderWithProviders(<OrdersPage />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders orders list', async () => {
    ordersState = { ...ordersState, data: [sampleOrder] }
    renderWithProviders(<OrdersPage />)
    await waitFor(() => {
      expect(screen.getByText('#ORD-001')).toBeInTheDocument()
    })
    expect(screen.getByText('R$ 150,50')).toBeInTheDocument()
    expect(screen.getByText(/CLT-001/)).toBeInTheDocument()
  })

  it('shows empty state when no orders', () => {
    renderWithProviders(<OrdersPage />)
    expect(screen.getByText('Nenhum pedido')).toBeInTheDocument()
  })

  it('shows error state on failure', () => {
    ordersState = { ...ordersState, error: new Error('boom') }
    renderWithProviders(<OrdersPage />)
    expect(screen.getByText('Não foi possível carregar os pedidos.')).toBeInTheDocument()
  })

  it('imprimir enfileira o cupom e confirma na impressora configurada', async () => {
    ordersState = { ...ordersState, data: [sampleOrder] }
    renderWithProviders(<OrdersPage />)

    const printBtn = await screen.findByRole('button', { name: /imprimir pedido ord-001/i })
    fireEvent.click(printBtn)

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/printer/print', { order_id: 'ORD-001' })
    })
    // Quem imprime é a impressora da máquina do operador: o toast promete
    // "na fila", não "impresso".
    await waitFor(() => {
      expect(screen.getByText(/cupom na fila de impressão/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/GT710/)).toBeInTheDocument()
  })

  it('imprimir sem impressora escolhida avisa o caminho em vez de fingir sucesso', async () => {
    apiGet.mockResolvedValue({ data: { ...statusComImpressora, status: 'NOT_CONFIGURED', printer_name: null } })
    ordersState = { ...ordersState, data: [sampleOrder] }
    renderWithProviders(<OrdersPage />)

    const printBtn = await screen.findByRole('button', { name: /imprimir pedido ord-001/i })
    fireEvent.click(printBtn)

    await waitFor(() => {
      expect(screen.getByText(/nenhuma impressora configurada/i)).toBeInTheDocument()
    })
  })

  it('imprimir com o app sem sinal avisa em vez de prometer impressão', async () => {
    // Impressora escolhida, mas o último relato do agente é velho: o app pode
    // estar fechado e o cupom ficar na fila — não dá para dizer "sai em instantes".
    apiGet.mockResolvedValue({ data: { ...statusComImpressora, stale: true } })
    ordersState = { ...ordersState, data: [sampleOrder] }
    renderWithProviders(<OrdersPage />)

    const printBtn = await screen.findByRole('button', { name: /imprimir pedido ord-001/i })
    fireEvent.click(printBtn)

    await waitFor(() => {
      expect(screen.getByText(/app de impressão está sem sinal/i)).toBeInTheDocument()
    })
    expect(screen.queryByText(/sai em instantes/i)).not.toBeInTheDocument()
  })

  it('print button shows error toast when API fails', async () => {
    apiPost.mockRejectedValueOnce(new Error('printer offline'))
    ordersState = { ...ordersState, data: [sampleOrder] }
    renderWithProviders(<OrdersPage />)

    const printBtn = await screen.findByRole('button', { name: /imprimir pedido ord-001/i })
    fireEvent.click(printBtn)

    await waitFor(() => {
      expect(screen.getByText(/não foi possível enviar para impressão/i)).toBeInTheDocument()
    })
    // Botão volta a habilitar após a falha
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /imprimir pedido ord-001/i })).toBeEnabled()
    })
  })
})
