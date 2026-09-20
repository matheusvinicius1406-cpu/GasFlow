import { screen, waitFor, fireEvent, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ReportsPage } from './ReportsPage'

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { apiClient } from '@/lib/api/client'
import { renderWithProviders } from '@/test/utils'

const periodo = {
  from: '2026-08-21',
  to: '2026-09-19',
  days: 30,
  total_receipts: '1500.00',
  total_expenses: '500.00',
  net_result: '1000.00',
  daily: [
    { date: '2026-09-18', receipts: '500.00', expenses: '200.00', net_result: '300.00' },
    { date: '2026-09-19', receipts: '1000.00', expenses: '300.00', net_result: '700.00' },
  ],
  previous: {
    from: '2026-07-22',
    to: '2026-08-20',
    total_receipts: '1000.00',
    total_expenses: '500.00',
    net_result: '500.00',
  },
  comparison: { receipts_pct: 50.0, expenses_pct: 0.0, net_pct: 100.0 },
}

const entregas = { days: 30, generated_at: '2026-09-19T12:00:00', by_day: [], by_driver: [], by_neighborhood: [] }

function mockGet() {
  vi.mocked(apiClient.get).mockImplementation((url: string) => {
    if (url === '/finance/reports/period') return Promise.resolve({ data: periodo })
    if (url === '/finance/cash/balance') return Promise.resolve({ data: { balance: '250.00' } })
    if (url === '/reports/deliveries') return Promise.resolve({ data: entregas })
    return Promise.reject(new Error(`url inesperada: ${url}`))
  })
}

/**
 * O total do período aparece DUAS vezes na tela (card de métrica e rodapé da
 * tabela), então o teste mira o card pelo `testid` em vez de buscar o texto
 * solto — que casaria com os dois.
 */
async function aguardarPeriodo() {
  await waitFor(() => expect(screen.getByTestId('metric-receipts')).toHaveTextContent('R$ 1.500,00'))
}

describe('ReportsPage (F10.9)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet()
    vi.spyOn(window, 'print').mockImplementation(() => undefined)
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:gasflow-test')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
  })

  afterEach(() => {
    ;(window as { gasflow?: unknown }).gasflow = undefined
  })

  it('carrega o período padrão de 30 dias com totais, saldo e comparação', async () => {
    renderWithProviders(<ReportsPage />)

    await aguardarPeriodo()
    expect(screen.getByTestId('metric-expenses')).toHaveTextContent('R$ 500,00')
    expect(screen.getByTestId('metric-net')).toHaveTextContent('R$ 1.000,00')
    expect(screen.getByTestId('metric-balance')).toHaveTextContent('R$ 250,00') // saldo em caixa

    expect(apiClient.get).toHaveBeenCalledWith('/finance/reports/period', { params: { days: 30 } })
    // Comparação visível: recebimentos +50%
    expect(screen.getAllByText('50,0%').length).toBeGreaterThan(0)
    expect(screen.getByText(/comparado com 22\/07\/2026/)).toBeInTheDocument()
  })

  it('mostra o intervalo do período no subtítulo e o detalhe dia a dia', async () => {
    renderWithProviders(<ReportsPage />)

    await waitFor(() => expect(screen.getByText(/21\/08\/2026 a 19\/09\/2026/)).toBeInTheDocument())
    expect(screen.getByText('Detalhe por dia')).toBeInTheDocument()
    expect(screen.getByText('18/09/2026')).toBeInTheDocument()
    expect(screen.getByText('19/09/2026')).toBeInTheDocument()
    expect(screen.getByText('Total')).toBeInTheDocument()
  })

  it('troca o filtro de período e refaz a consulta', async () => {
    renderWithProviders(<ReportsPage />)
    await aguardarPeriodo()

    // O bloco de entregas tem o próprio recorte 7/30/90 — o filtro do
    // relatório é o do grupo "Período do relatório".
    const filtroPeriodo = within(screen.getByRole('group', { name: 'Período do relatório' }))
    fireEvent.click(filtroPeriodo.getByRole('button', { name: '7 dias' }))

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith('/finance/reports/period', { params: { days: 7 } })
    })
  })

  it('exporta CSV do período (arquivo gerado no cliente)', async () => {
    renderWithProviders(<ReportsPage />)
    await aguardarPeriodo()

    fireEvent.click(screen.getByRole('button', { name: /exportar csv/i }))

    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalledTimes(1))
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1)
  })

  it('imprimir usa a ponte do Electron quando existir (e não o diálogo do navegador)', async () => {
    const exportCurrentViewPdf = vi.fn().mockResolvedValue({ ok: true })
    ;(window as { gasflow?: unknown }).gasflow = { exportCurrentViewPdf }

    renderWithProviders(<ReportsPage />)
    await aguardarPeriodo()

    fireEvent.click(screen.getByRole('button', { name: /imprimir/i }))

    await waitFor(() => expect(exportCurrentViewPdf).toHaveBeenCalledTimes(1))
    expect(window.print).not.toHaveBeenCalled()
  })

  it('fora do Electron, imprimir cai no diálogo do sistema', async () => {
    renderWithProviders(<ReportsPage />)
    await aguardarPeriodo()

    fireEvent.click(screen.getByRole('button', { name: /imprimir/i }))

    await waitFor(() => expect(window.print).toHaveBeenCalledTimes(1))
  })

  it('mostra o spinner enquanto o período não chegou', () => {
    vi.mocked(apiClient.get).mockImplementation(() => new Promise(() => {}))

    const { container } = renderWithProviders(<ReportsPage />)

    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('erro na consulta mostra o estado de erro em vez de números zerados', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('boom'))

    renderWithProviders(<ReportsPage />)

    expect(await screen.findByText('Não foi possível carregar os relatórios.')).toBeInTheDocument()
  })

  it('período sem movimento explica em vez de mostrar gráfico vazio', async () => {
    vi.mocked(apiClient.get).mockImplementation((url: string) => {
      if (url === '/finance/reports/period') {
        return Promise.resolve({
          data: {
            ...periodo,
            total_receipts: '0.00',
            total_expenses: '0.00',
            net_result: '0.00',
            daily: [{ date: '2026-09-19', receipts: '0.00', expenses: '0.00', net_result: '0.00' }],
          },
        })
      }
      if (url === '/finance/cash/balance') return Promise.resolve({ data: { balance: '0.00' } })
      return Promise.resolve({ data: entregas })
    })

    renderWithProviders(<ReportsPage />)

    expect(await screen.findByText(/Sem movimentações neste período/i)).toBeInTheDocument()
  })
})
