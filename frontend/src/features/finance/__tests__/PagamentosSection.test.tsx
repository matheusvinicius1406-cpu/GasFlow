import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { PagamentosSection } from '../sections/PagamentosSection'
import type { MethodBreakdownData } from '../useAnalyticsData'

/** P7 — Pagamentos por forma. */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const pagamentos: MethodBreakdownData = {
  from: '2026-09-01',
  to: '2026-09-24',
  days: 30,
  total: 4000,
  items: [
    { method: 'PIX', total: 3000, pct: 75 },
    { method: 'CASH', total: 1000, pct: 25 },
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
  if (url === '/finance/reports/methods') return pagamentos
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('PagamentosSection (P7 — dado)', () => {
  it('lista o total, a forma principal e a distribuição', () => {
    renderWithProviders(<PagamentosSection data={pagamentos} />)

    expect(within(screen.getByTestId('pagamentos-total')).getByText('R$ 4.000,00')).toBeInTheDocument()
    expect(within(screen.getByTestId('pagamentos-principal')).getByText('PIX')).toBeInTheDocument()
    expect(within(screen.getByTestId('pagamentos-formas')).getByText('2')).toBeInTheDocument()
    expect(screen.getByText('Dinheiro')).toBeInTheDocument()
  })

  it('expõe as barras de proporção como progressbar acessível', () => {
    renderWithProviders(<PagamentosSection data={pagamentos} />)

    const pix = screen.getByRole('progressbar', { name: 'Proporção de PIX no total recebido' })
    expect(pix).toHaveAttribute('aria-valuenow', '75')
    const dinheiro = screen.getByRole('progressbar', { name: 'Proporção de Dinheiro no total recebido' })
    expect(dinheiro).toHaveAttribute('aria-valuenow', '25')
  })
})

describe('PagamentosSection (P7 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=pagamentos',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/reports/methods'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=pagamentos' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state sem pagamentos', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data: url === '/finance/reports/methods' ? { ...pagamentos, total: 0, items: [] } : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=pagamentos' })

    expect(await screen.findByRole('heading', { name: 'Nenhum pagamento no período' })).toBeInTheDocument()
  })
})
