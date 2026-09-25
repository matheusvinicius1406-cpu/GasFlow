import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { ProjecaoSection } from '../sections/ProjecaoSection'
import type { ProjectionData } from '../useAnalyticsData'

/**
 * P6 — Projeção: KPIs do modelo declarado + série de saldo. O rótulo
 * honesto (`model`) é exibido para não vender precisão que não existe.
 */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const projecao: ProjectionData = {
  generated_at: '2026-09-24T12:00:00',
  horizon: 30,
  current_balance: 1200,
  expected_in: 800,
  avg_daily_expenses: 20,
  expected_out: 600,
  projected_balance: 1400,
  daily: [
    { date: '2026-09-25', inflow: 0, outflow: 20, balance: 1180 },
    { date: '2026-09-26', inflow: 800, outflow: 20, balance: 1960 },
  ],
  model: 'Saldo atual + recebíveis com vencimento − média histórica de despesas.',
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
  if (url === '/finance/reports/projection') return projecao
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('ProjecaoSection (P6 — dado)', () => {
  it('renderiza saldos, modelo declarado e a série', () => {
    renderWithProviders(<ProjecaoSection data={projecao} />)

    expect(within(screen.getByTestId('projecao-saldo-atual')).getByText('R$ 1.200,00')).toBeInTheDocument()
    expect(
      within(screen.getByTestId('projecao-saldo-projetado')).getByText('R$ 1.400,00')
    ).toBeInTheDocument()
    expect(screen.getByText('Como a projeção é calculada')).toBeInTheDocument()
    expect(screen.getByText(/média histórica de despesas/)).toBeInTheDocument()
    expect(screen.getByText('Saldo projetado por dia')).toBeInTheDocument()
  })
})

describe('ProjecaoSection (P6 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=projecao',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/reports/projection'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=projecao' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state sem série diária', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data: url === '/finance/reports/projection' ? { ...projecao, daily: [] } : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=projecao' })

    expect(await screen.findByRole('heading', { name: 'Projeção indisponível' })).toBeInTheDocument()
  })
})
