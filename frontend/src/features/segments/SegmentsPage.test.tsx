import { screen, waitFor } from '@testing-library/react'
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
import { SegmentsPage } from './SegmentsPage'

const vipSegment = {
  id: 1,
  name: 'VIP 3+ Pedidos',
  description: 'Clientes com 3 ou mais pedidos',
  rules: [{ field: 'total_orders', operator: 'greater_than', value: 2 }],
  rule_logic: 'AND',
  status: 'ACTIVE',
  member_count: 3,
  last_evaluated_at: '2026-08-01T00:00:00',
  created_at: '2026-07-01T00:00:00',
  updated_at: '2026-08-01T00:00:00',
}

const draftSegment = {
  id: 2,
  name: 'Inativos 90d',
  description: '',
  rules: [
    { field: 'days_since_last_order', operator: 'greater_than', value: 90 },
    { field: 'client_type', operator: 'equals', value: 'RESIDENCIAL' },
  ],
  rule_logic: 'AND',
  status: 'DRAFT',
  member_count: 0,
  last_evaluated_at: null,
  created_at: '2026-07-10T00:00:00',
  updated_at: '2026-07-10T00:00:00',
}

describe('SegmentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockResolvedValue({ data: [] })
    vi.mocked(apiClient.post).mockResolvedValue({ data: { success: true } })
    vi.mocked(apiClient.put).mockResolvedValue({ data: { success: true } })
    vi.mocked(apiClient.delete).mockResolvedValue({ data: { success: true } })
  })

  it('shows the empty state when there are no segments', async () => {
    renderWithProviders(<SegmentsPage />)
    await waitFor(() => {
      expect(screen.getByText('Nenhum segmento criado')).toBeInTheDocument()
    })
  })

  it('renders the segments list with status, count and rules', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [vipSegment, draftSegment] })
    renderWithProviders(<SegmentsPage />)

    await waitFor(() => {
      expect(screen.getByText('VIP 3+ Pedidos')).toBeInTheDocument()
    })
    expect(screen.getByText('Inativos 90d')).toBeInTheDocument()
    expect(screen.getByText('Ativo')).toBeInTheDocument()
    expect(screen.getByText('Rascunho')).toBeInTheDocument()
    expect(screen.getByText('3 clientes')).toBeInTheDocument()
    expect(screen.getByText('1 regra')).toBeInTheDocument()
    expect(screen.getByText('2 regras')).toBeInTheDocument()
  })

  it('shows the error state when the fetch fails', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('boom'))
    renderWithProviders(<SegmentsPage />)

    await waitFor(() => {
      expect(
        screen.getByText('Não foi possível carregar os segmentos.')
      ).toBeInTheDocument()
    })
  })

  it('retries after an error when clicking the retry button', async () => {
    vi.mocked(apiClient.get)
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce({ data: [vipSegment] })
    renderWithProviders(<SegmentsPage />)

    const retry = await screen.findByRole('button', { name: /Tentar novamente/i })
    retry.click()

    await waitFor(() => {
      expect(screen.getByText('VIP 3+ Pedidos')).toBeInTheDocument()
    })
  })

  it('evaluates a segment and refreshes the list', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [vipSegment] })
    renderWithProviders(<SegmentsPage />)

    const evaluate = await screen.findByRole('button', { name: 'Avaliar' })
    evaluate.click()

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/segments/1/evaluate')
    })
    // fetchSegments() runs again after evaluation.
    expect(apiClient.get).toHaveBeenCalledTimes(2)
  })
})
