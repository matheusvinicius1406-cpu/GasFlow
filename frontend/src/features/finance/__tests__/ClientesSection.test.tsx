import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { ClientesSection } from '../sections/ClientesSection'
import type { ClientesData } from '../useAnalyticsData'

/**
 * P7 — Clientes: aging dos recebíveis + lista de cobrança dos vencidos.
 */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const clientes: ClientesData = {
  summary: {
    generated_at: '2026-09-24T12:00:00',
    open_count: 5,
    open_total: 2500,
    overdue_count: 2,
    overdue_total: 700,
    buckets: [
      { bucket: '0-30', count: 3, total: 1500 },
      { bucket: '31-60', count: 1, total: 300 },
      { bucket: '61-90', count: 0, total: 0 },
      { bucket: '90+', count: 1, total: 700 },
    ],
  },
  overdue: [
    {
      id: 1,
      order_codigo: 'PED9',
      customer_codigo: 'CLI1',
      original_amount: 700,
      paid_amount: 0,
      remaining_amount: 700,
      due_date: '2020-01-01',
      status: 'OVERDUE',
      created_at: '2020-01-01',
      settled_at: null,
    },
  ],
}

const periodo = {
  from: '2026-09-01',
  to: '2026-09-24',
  days: 30,
  total_receipts: 0,
  total_expenses: 0,
  net_result: 0,
  daily: [],
  previous: { from: '2026-08-01', to: '2026-08-31', total_receipts: 0, total_expenses: 0, net_result: 0 },
  comparison: { receipts_pct: null, expenses_pct: null, net_pct: null },
}

function fixtureFor(url: string): unknown {
  if (url === '/finance/receivables/summary') return clientes.summary
  if (url === '/finance/receivables') return { items: clientes.overdue, total: 1, page: 1, page_size: 50, total_pages: 1 }
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('ClientesSection (P7 — dado)', () => {
  it('mostra aging, totais e a lista de cobrança', () => {
    renderWithProviders(<ClientesSection data={clientes} />)

    expect(within(screen.getByTestId('clientes-aberto')).getByText('R$ 2.500,00')).toBeInTheDocument()
    expect(within(screen.getByTestId('clientes-atraso')).getByText('R$ 700,00')).toBeInTheDocument()
    expect(screen.getByText('90+ dias')).toBeInTheDocument()
    expect(screen.getByText('#PED9')).toBeInTheDocument()
    expect(screen.getByText('Ação manual')).toBeInTheDocument()
  })
})

describe('ClientesSection (P7 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=clientes',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/receivables/summary'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=clientes' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state sem recebíveis', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data:
          url === '/finance/receivables/summary'
            ? { ...clientes.summary, open_count: 0, open_total: 0, overdue_count: 0, overdue_total: 0, buckets: [] }
            : url === '/finance/receivables'
              ? { items: [], total: 0, page: 1, page_size: 50, total_pages: 1 }
              : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=clientes' })

    expect(await screen.findByRole('heading', { name: 'Nenhum recebível em aberto' })).toBeInTheDocument()
  })
})
