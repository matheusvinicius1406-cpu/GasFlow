import { fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { SimuladorSection } from '../sections/SimuladorSection'
import type { SimuladorData } from '../useAnalyticsData'

/** P7 — Simulador what-if (cálculo no cliente, não grava nada). */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const simulador: SimuladorData = {
  period: {
    from: '2026-09-01',
    to: '2026-09-24',
    days: 30,
    total_receipts: 2000,
    total_expenses: 500,
    net_result: 1000,
    daily: [{ date: '2026-09-24', receipts: 2000, expenses: 500, net_result: 1000 }],
    comparison: { receipts_pct: null, expenses_pct: null, net_pct: null },
  },
  receivables: [
    {
      id: 1,
      order_codigo: 'PED1',
      customer_codigo: 'CLI1',
      original_amount: 400,
      paid_amount: 0,
      remaining_amount: 400,
      due_date: '2026-10-01',
      status: 'OPEN',
      created_at: '2026-09-01',
      settled_at: null,
    },
    {
      id: 2,
      order_codigo: 'PED2',
      customer_codigo: 'CLI2',
      original_amount: 100,
      paid_amount: 0,
      remaining_amount: 100,
      due_date: '2026-10-02',
      status: 'OPEN',
      created_at: '2026-09-01',
      settled_at: null,
    },
  ],
}

function fixtureFor(url: string): unknown {
  if (url === '/finance/reports/period') return simulador.period
  if (url === '/finance/receivables')
    return { items: simulador.receivables, total: 2, page: 1, page_size: 100, total_pages: 1 }
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('SimuladorSection (P7 — dado)', () => {
  it('projeta o resultado somando recebíveis em aberto', () => {
    renderWithProviders(<SimuladorSection data={simulador} />)

    expect(within(screen.getByTestId('simulador-atual')).getByText('R$ 1.000,00')).toBeInTheDocument()
    expect(within(screen.getByTestId('simulador-receber')).getByText('R$ 500,00')).toBeInTheDocument()
    expect(within(screen.getByTestId('simulador-resultado')).getByText('R$ 1.500,00')).toBeInTheDocument()
  })

  it('recalcula com a redução de despesas', () => {
    renderWithProviders(<SimuladorSection data={simulador} />)

    fireEvent.change(screen.getByLabelText('Percentual de redução de despesas'), {
      target: { value: '50' },
    })

    expect(within(screen.getByTestId('simulador-economia')).getByText('R$ 250,00')).toBeInTheDocument()
    expect(within(screen.getByTestId('simulador-resultado')).getByText('R$ 1.750,00')).toBeInTheDocument()
  })
})

describe('SimuladorSection (P7 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=simulador',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/reports/period'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=simulador' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state sem dados para simular', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data: url === '/finance/reports/period' ? { ...simulador.period, daily: [] } : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=simulador' })

    expect(await screen.findByRole('heading', { name: 'Sem dados para simular' })).toBeInTheDocument()
  })
})
