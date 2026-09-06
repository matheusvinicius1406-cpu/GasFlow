import { fireEvent, screen, waitFor } from '@testing-library/react'
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
import { ReorderPage } from './ReorderPage'

const summary = {
  total_customers: 12,
  ready_count: 3,
  due_count: 2,
  overdue_count: 1,
  dormant_count: 6,
  high_confidence_count: 4,
  medium_confidence_count: 5,
  low_confidence_count: 3,
}

const opportunities = [
  {
    customer_codigo: 'CLT-001',
    customer_nome: 'Maria Silva',
    total_orders: 4,
    total_spent: 480,
    average_ticket: 120,
    days_since_last_order: 25,
    last_order_date: '2026-08-10',
    expected_reorder_date: '2026-09-05',
    expected_interval_days: 30,
    reorder_score: 82,
    confidence: 'HIGH',
    status: 'OVERDUE',
    recommended_product: 'P13',
    days_overdue: 3,
    avg_days_between_orders: 28,
    order_dates: ['2026-07-01', '2026-07-15', '2026-07-29', '2026-08-10'],
  },
  {
    customer_codigo: 'CLT-002',
    customer_nome: 'João Souza',
    total_orders: 1,
    total_spent: 130,
    average_ticket: 130,
    days_since_last_order: 40,
    last_order_date: '2026-07-25',
    expected_reorder_date: null,
    expected_interval_days: null,
    reorder_score: 30,
    confidence: 'LOW',
    status: 'DORMANT',
    recommended_product: null,
    days_overdue: null,
    avg_days_between_orders: null,
    order_dates: ['2026-07-25'],
  },
]

function mockSuccess() {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/reorder/summary') return { data: summary }
    if (url === '/reorder/opportunities') return { data: { opportunities } }
    return { data: {} }
  })
}

const render = () => renderWithProviders(<ReorderPage />)

describe('ReorderPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSuccess()
  })

  it('shows the loading spinner while fetching', () => {
    vi.mocked(apiClient.get).mockImplementation(
      () => new Promise(() => {}) as never,
    )
    const { container } = render()
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders the KPI summary and opportunities table', async () => {
    render()

    await waitFor(() => {
      expect(screen.getByText('Maria Silva')).toBeInTheDocument()
    })
    // KPI cards (títulos também aparecem como options dos filtros → usar getAll)
    expect(screen.getAllByText('Próximos').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Na Janela').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Atrasados').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Inativos').length).toBeGreaterThan(0)
    // Table
    expect(screen.getByText('João Souza')).toBeInTheDocument()
    expect(screen.getAllByText('Atrasado').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Inativo').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Alta').length).toBeGreaterThan(0)
    expect(screen.getAllByText('P13').length).toBeGreaterThan(0)
    expect(screen.getByText('Oportunidades (2)')).toBeInTheDocument()
  })

  it('shows the error state and retries', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('boom'))
    render()

    await waitFor(() => {
      expect(screen.getByText('Erro ao carregar dados de recompra')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Tentar novamente/i }))
    await waitFor(() => {
      expect(screen.getByText('Maria Silva')).toBeInTheDocument()
    })
  })

  it('shows the empty state when no opportunities match', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === '/reorder/summary') return { data: summary }
      if (url === '/reorder/opportunities') return { data: { opportunities: [] } }
      return { data: {} }
    })
    render()

    await waitFor(() => {
      expect(screen.getByText('Nenhuma oportunidade encontrada')).toBeInTheDocument()
    })
  })

  it('filters the table by search text', async () => {
    render()

    await waitFor(() => {
      expect(screen.getByText('Maria Silva')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByPlaceholderText('Buscar por nome ou código...'), {
      target: { value: 'João' },
    })

    expect(screen.queryByText('Maria Silva')).not.toBeInTheDocument()
    expect(screen.getByText('João Souza')).toBeInTheDocument()
  })
})
