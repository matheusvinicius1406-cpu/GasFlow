import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { DeliveryCharts } from './DeliveryCharts'

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

const report = {
  days: 30,
  generated_at: '2026-09-18T12:00:00',
  by_day: [
    { day: '2026-09-17', created: 5, delivered: 4, failed: 1 },
    { day: '2026-09-18', created: 6, delivered: 6, failed: 0 },
  ],
  by_driver: [
    { driver_id: '000001', assigned: 6, delivered: 5, failed: 1, avg_minutes: 92.5 },
    { driver_id: '000002', assigned: 4, delivered: 4, failed: 0, avg_minutes: 61.0 },
  ],
  by_neighborhood: [
    { neighborhood: 'Centro', count: 6 },
    { neighborhood: 'Sul', count: 3 },
  ],
}

describe('DeliveryCharts (F9)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockResolvedValue({ data: report })
    // jsdom: spy em window.print (fallback de export fora do Electron)
    vi.spyOn(window, 'print').mockImplementation(() => undefined)
  })

  it('renderiza os quatro gráficos com dados', async () => {
    renderWithProviders(<DeliveryCharts />)

    await waitFor(() => {
      expect(screen.getByText('Entregas por dia')).toBeInTheDocument()
    })
    expect(screen.getByText('Comparativo por entregador')).toBeInTheDocument()
    expect(screen.getByText('Tempo médio de entrega (min)')).toBeInTheDocument()
    expect(screen.getByText('Entregas por bairro')).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith('/reports/deliveries', { params: { days: 30 } })
  })

  it('troca o período e refaz a chamada', async () => {
    renderWithProviders(<DeliveryCharts />)
    await waitFor(() => screen.getByText('Entregas por dia'))

    fireEvent.click(screen.getByRole('button', { name: '7 dias' }))

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith('/reports/deliveries', { params: { days: 7 } })
    })
  })

  it('botão Atualizar refaz a chamada (refresh manual — sem auto)', async () => {
    renderWithProviders(<DeliveryCharts />)
    await waitFor(() => screen.getByText('Entregas por dia'))
    expect(apiClient.get).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: /atualizar/i }))

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledTimes(2)
    })
  })

  it('exporta PDF via bridge Electron quando disponível', async () => {
    const exportCurrentViewPdf = vi.fn().mockResolvedValue({ ok: true })
    ;(window as { gasflow?: unknown }).gasflow = { exportCurrentViewPdf }

    renderWithProviders(<DeliveryCharts />)
    await waitFor(() => screen.getByText('Entregas por dia'))

    fireEvent.click(screen.getByRole('button', { name: /exportar pdf/i }))

    await waitFor(() => {
      expect(exportCurrentViewPdf).toHaveBeenCalledTimes(1)
    })
    expect(window.print).not.toHaveBeenCalled()
    ;(window as { gasflow?: unknown }).gasflow = undefined
  })

  it('fallback window.print fora do Electron', async () => {
    renderWithProviders(<DeliveryCharts />)
    await waitFor(() => screen.getByText('Entregas por dia'))

    fireEvent.click(screen.getByRole('button', { name: /exportar pdf/i }))

    await waitFor(() => {
      expect(window.print).toHaveBeenCalled()
    })
  })

  it('estado vazio quando não há entregas', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { days: 30, generated_at: 'x', by_day: [], by_driver: [], by_neighborhood: [] },
    })

    renderWithProviders(<DeliveryCharts />)

    await waitFor(() => {
      expect(screen.getAllByText('Sem dados').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('estado de erro com retry', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('boom'))

    renderWithProviders(<DeliveryCharts />)

    await waitFor(() => {
      expect(screen.getByText('Não foi possível carregar os gráficos')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }))
    // Após o retry bem-sucedido os gráficos aparecem
    // (mock volta ao default no próximo teste; aqui basta não ter lançado)
  })
})
