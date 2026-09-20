import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { PrinterSettings } from './PrinterSettings'

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

const statusBackend = {
  status: 'ONLINE',
  printer_name: 'GT710',
  detail: '',
  reported_at: '2026-09-19T12:00:00',
  stale: false,
  pending_jobs: 1,
  failed_jobs: 1,
  expired_jobs: 0,
  total_jobs_today: 4,
}

const expiredJob = {
  id: 'print-3',
  order_id: 'ORD3',
  status: 'EXPIRED',
  is_reprint: false,
  attempts: 1,
  error: 'cupom de dia anterior — não sai sozinho; reimprima se precisar',
  created_at: '2026-09-18T23:50:00',
  completed_at: null,
}

const jobs = {
  jobs: [
    {
      id: 'print-1',
      order_id: 'ORD1',
      status: 'FAILED',
      is_reprint: false,
      attempts: 2,
      error: 'sem papel',
      created_at: '2026-09-19T12:00:00',
      completed_at: null,
    },
    {
      id: 'print-2',
      order_id: 'ORD2',
      status: 'COMPLETED',
      is_reprint: false,
      attempts: 1,
      error: null,
      created_at: '2026-09-19T11:00:00',
      completed_at: '2026-09-19T11:00:05',
    },
  ],
}

const localStatus = {
  running: true,
  printerName: 'GT710',
  state: 'ONLINE' as const,
  printed: 7,
  replayed: 0,
  failed: 1,
  lastTickAt: Date.now(),
  lastError: '',
}

type Bridge = Record<string, unknown>

function setBridge(bridge: Bridge | undefined) {
  ;(window as { gasflow?: unknown }).gasflow = bridge
}

describe('PrinterSettings (F10.7/F10.8)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockImplementation((url: string) => {
      if (url === '/printer/status') return Promise.resolve({ data: statusBackend })
      if (url === '/printer/jobs') return Promise.resolve({ data: jobs })
      return Promise.reject(new Error(`url inesperada: ${url}`))
    })
    vi.mocked(apiClient.post).mockResolvedValue({ data: { success: true, job: { id: 'print-1', is_reprint: false } } })
    vi.spyOn(window, 'print').mockImplementation(() => undefined)
  })

  afterEach(() => {
    setBridge(undefined)
  })

  it('sem o app (navegador): explica onde configurar, mas mostra a fila do servidor', async () => {
    renderWithProviders(<PrinterSettings />)

    expect(await screen.findByText(/Configuração da impressora só no aplicativo/i)).toBeInTheDocument()
    expect(screen.getByText('#ORD1')).toBeInTheDocument()
    expect(screen.getByText('sem papel')).toBeInTheDocument()
    // Sem ponte não há como testar a impressora
    expect(screen.queryByRole('button', { name: /testar impressão/i })).not.toBeInTheDocument()
  })

  it('no app: lista impressoras, mostra o estado e permite testar a impressão', async () => {
    const printerSetName = vi.fn().mockResolvedValue({ ok: true, printerName: 'GT710' })
    const printerTest = vi.fn().mockResolvedValue({ ok: true, printerName: 'GT710' })
    setBridge({
      printerStatus: vi.fn().mockResolvedValue({ ok: true, status: localStatus }),
      printerList: vi.fn().mockResolvedValue({
        ok: true,
        printers: [
          { name: 'GT710', displayName: 'GT710', isDefault: true },
          { name: 'PDF', displayName: 'Microsoft Print to PDF', isDefault: false },
        ],
      }),
      printerSetName,
      printerTest,
    })

    renderWithProviders(<PrinterSettings />)

    await waitFor(() => expect(screen.getByText('Pronta')).toBeInTheDocument())
    expect(screen.getByText('Microsoft Print to PDF')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Impressora instalada nesta máquina/i), {
      target: { value: 'PDF' },
    })
    await waitFor(() => expect(printerSetName).toHaveBeenCalledWith('PDF'))

    fireEvent.click(screen.getByRole('button', { name: /testar impressão/i }))
    await waitFor(() => expect(printerTest).toHaveBeenCalledTimes(1))
  })

  it('app sem sinal: avisa que o estado é velho em vez de mostrar a fila parada como normal', async () => {
    vi.mocked(apiClient.get).mockImplementation((url: string) => {
      if (url === '/printer/status') {
        return Promise.resolve({
          data: { ...statusBackend, stale: true, reported_at: '2026-09-19T09:00:00' },
        })
      }
      return Promise.resolve({ data: jobs })
    })

    renderWithProviders(<PrinterSettings />)

    expect(await screen.findByText(/Sem sinal do app de impressão/i)).toBeInTheDocument()
    // Os 2 cupons parados na fila aparecem no aviso (nada foi perdido)
    expect(screen.getByText(/2 cupom\(ns\) esperando na fila/i)).toBeInTheDocument()
  })

  it('sem sinal e sem fila: não assusta com cupom que não existe', async () => {
    vi.mocked(apiClient.get).mockImplementation((url: string) => {
      if (url === '/printer/status') {
        return Promise.resolve({
          data: { ...statusBackend, stale: true, pending_jobs: 0, failed_jobs: 0 },
        })
      }
      return Promise.resolve({ data: { jobs: [] } })
    })

    renderWithProviders(<PrinterSettings />)

    expect(await screen.findByText(/Sem sinal do app de impressão/i)).toBeInTheDocument()
    expect(screen.getByText(/Nenhum cupom esperando agora/i)).toBeInTheDocument()
  })

  it('sem impressora escolhida: avisa e desabilita o teste', async () => {
    setBridge({
      printerStatus: vi.fn().mockResolvedValue({
        ok: true,
        status: { ...localStatus, printerName: '', state: 'NOT_CONFIGURED' },
      }),
      printerList: vi.fn().mockResolvedValue({ ok: true, printers: [] }),
      printerSetName: vi.fn(),
      printerTest: vi.fn(),
    })

    renderWithProviders(<PrinterSettings />)

    expect(await screen.findByText(/Nenhuma impressora escolhida/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /testar impressão/i })).toBeDisabled()
  })

  it('mostra o erro real da impressora em vez de "falha ao imprimir"', async () => {
    setBridge({
      printerStatus: vi.fn().mockResolvedValue({
        ok: true,
        status: { ...localStatus, state: 'ERROR', lastError: 'OpenPrinter falhou (impressora não encontrada: GT710)' },
      }),
      printerList: vi.fn().mockResolvedValue({ ok: true, printers: [] }),
      printerSetName: vi.fn(),
      printerTest: vi.fn(),
    })

    renderWithProviders(<PrinterSettings />)

    expect(await screen.findByText(/OpenPrinter falhou/)).toBeInTheDocument()
    expect(screen.getByText('Com erro')).toBeInTheDocument()
  })

  it('cupom de dia anterior aparece como vencido e sai só na reimpressão', async () => {
    setBridge({
      printerStatus: vi.fn().mockResolvedValue({ ok: true, status: localStatus }),
      printerList: vi.fn().mockResolvedValue({ ok: true, printers: [] }),
      printerSetName: vi.fn(),
      printerTest: vi.fn(),
    })
    vi.mocked(apiClient.get).mockImplementation((url: string) => {
      if (url === '/printer/status') return Promise.resolve({ data: { ...statusBackend, expired_jobs: 1 } })
      return Promise.resolve({ data: { jobs: [expiredJob] } })
    })
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { success: true, job: { id: 'print-4', is_reprint: true } },
    })

    renderWithProviders(<PrinterSettings />)

    expect(await screen.findByText('Vencido')).toBeInTheDocument()
    expect(screen.getByText(/Cupons de dia anterior não saíram/i)).toBeInTheDocument()
    // O vencido conta como atenção na fila e tem card próprio nos números
    expect(screen.getByText(/aguardando atenção/i)).toBeInTheDocument()
    expect(screen.getByText('Vencidos')).toBeInTheDocument()

    // Reimprimir é ação explícita do operador: o backend cria um job novo
    // (carimbo de agora), que passa pelo corte do dia.
    fireEvent.click(screen.getByRole('button', { name: /reimprimir/i }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/printer/jobs/print-3/retry'))
  })

  it('reimpressão: job concluído gera novo job; job falhado é reenfileirado', async () => {
    setBridge({
      printerStatus: vi.fn().mockResolvedValue({ ok: true, status: localStatus }),
      printerList: vi.fn().mockResolvedValue({ ok: true, printers: [] }),
      printerSetName: vi.fn(),
      printerTest: vi.fn(),
    })

    renderWithProviders(<PrinterSettings />)
    await screen.findByText('#ORD1')

    fireEvent.click(screen.getByRole('button', { name: /tentar de novo/i }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/printer/jobs/print-1/retry'))

    fireEvent.click(screen.getByRole('button', { name: /reimprimir/i }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/printer/jobs/print-2/retry'))
  })
})
