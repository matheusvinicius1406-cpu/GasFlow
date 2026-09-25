import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { DreSection } from '../sections/DreSection'
import type { DreData } from '../useAnalyticsData'

/**
 * P6 — DRE: o dado renderiza a cascata e o CMV parcial; o shell cobre
 * loading / error / empty da seção.
 */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const dre: DreData = {
  from: '2026-09-01',
  to: '2026-09-24',
  days: 30,
  revenue: 10000,
  cmv: 4000,
  gross_profit: 6000,
  expenses: 1500,
  result: 4500,
  cmv_coverage: 80,
  expense_items: [
    { category: 'FUEL', total: 1000, pct: 66.7 },
    { category: 'TAX', total: 500, pct: 33.3 },
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
  if (url === '/finance/reports/dre') return dre
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('DreSection (P6 — dado)', () => {
  it('renderiza KPIs, cascata e despesas por categoria', () => {
    renderWithProviders(<DreSection data={dre} />)

    expect(within(screen.getByTestId('dre-receita')).getByText('R$ 10.000,00')).toBeInTheDocument()
    expect(within(screen.getByTestId('dre-lucro-bruto')).getByText('R$ 6.000,00')).toBeInTheDocument()
    expect(within(screen.getByTestId('dre-resultado')).getByText('R$ 4.500,00')).toBeInTheDocument()
    expect(screen.getByText('(−) CMV')).toBeInTheDocument()
    expect(screen.getByText('Combustível')).toBeInTheDocument()
    expect(screen.getByText('CMV parcial')).toBeInTheDocument()
  })

  it('some o aviso quando o CMV cobre toda a receita', () => {
    renderWithProviders(<DreSection data={{ ...dre, cmv_coverage: 100 }} />)
    expect(screen.queryByText('CMV parcial')).toBeNull()
  })
})

describe('DreSection (P6 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
  })

  it('mostra loading enquanto o relatório não chega', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=dre',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry quando o endpoint falha', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/reports/dre'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=dre' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
    expect(screen.getByText('Não foi possível carregar os dados.')).toBeInTheDocument()
  })

  it('mostra empty state quando não há receita nem despesa', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data:
          url === '/finance/reports/dre'
            ? { ...dre, revenue: 0, cmv: 0, gross_profit: 0, expenses: 0, result: 0, expense_items: [] }
            : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=dre' })

    expect(
      await screen.findByRole('heading', { name: 'Sem movimentações no período' })
    ).toBeInTheDocument()
  })
})
