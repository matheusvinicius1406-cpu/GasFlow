import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

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
import { HeatmapPage } from './HeatmapPage'

const heatmapData = {
  period_days: 30,
  generated_at: '2026-09-18T12:00:00',
  cached: false,
  total: 5,
  neighborhoods: [
    { neighborhood: 'Centro', count: 3, center: { lat: -30.03, lng: -51.22 } },
    { neighborhood: 'Moinhos', count: 2, center: { lat: -30.0, lng: -51.2 } },
  ],
}

describe('HeatmapPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renderiza o mapa e o ranking com os dados do período', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: heatmapData })

    renderWithProviders(<HeatmapPage />)

    await waitFor(() => {
      expect(screen.getByText(/5 entrega\(s\) em 30 dias/)).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Mapa de calor de entregas por bairro')).toBeInTheDocument()
    expect(screen.getByText('Centro')).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith('/reports/heatmap', { params: { days: 30 } })
  })

  it('troca o filtro de período e refaz a chamada', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { ...heatmapData, period_days: 7, total: 2 } })

    renderWithProviders(<HeatmapPage />)
    await waitFor(() => screen.getByText(/30 dias/))

    fireEvent.click(screen.getByRole('button', { name: '7 dias' }))

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith('/reports/heatmap', { params: { days: 7 } })
    })
    // O card reflete o novo período (o botão "7 dias" também casa o texto,
    // então usamos findAll e verificamos que há mais de um match: botão + card)
    await waitFor(() => {
      expect(screen.getAllByText(/7 dias/).length).toBeGreaterThanOrEqual(2)
    })
  })

  it('estado vazio quando não há entregas no período', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { period_days: 7, generated_at: 'x', cached: false, total: 0, neighborhoods: [] },
    })

    renderWithProviders(<HeatmapPage />)

    await waitFor(() => {
      expect(screen.getByText('Sem entregas no período.')).toBeInTheDocument()
    })
  })

  it('mostra erro com retry quando a API falha', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('boom'))

    renderWithProviders(<HeatmapPage />)

    await waitFor(() => {
      expect(screen.getByText('Não foi possível carregar o mapa de calor.')).toBeInTheDocument()
    })
  })
})
