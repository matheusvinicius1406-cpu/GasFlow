import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { TendenciaSection } from '../sections/TendenciaSection'
import type { PeriodData } from '../useVisaoGeralData'

/** P7 — Tendência: média móvel 7d + regressão linear (cálculo no cliente). */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const periodo: PeriodData = {
  from: '2026-09-01',
  to: '2026-09-10',
  days: 10,
  total_receipts: 5500,
  total_expenses: 0,
  net_result: 5500,
  daily: Array.from({ length: 10 }, (_, i) => ({
    date: `2026-09-${String(i + 1).padStart(2, '0')}`,
    receipts: (i + 1) * 100,
    expenses: 0,
    net_result: (i + 1) * 100,
  })),
  comparison: { receipts_pct: null, expenses_pct: null, net_pct: null },
}

function fixtureFor(url: string): unknown {
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('TendenciaSection (P7 — dado)', () => {
  it('calcula média diária, tendência e projeção', () => {
    renderWithProviders(<TendenciaSection data={periodo} />)

    expect(within(screen.getByTestId('tendencia-media')).getByText('R$ 550,00')).toBeInTheDocument()
    expect(screen.getByText('Tendência por dia')).toBeInTheDocument()
    expect(screen.getByText('Projeção 15 dias')).toBeInTheDocument()
    expect(screen.getByText('Cálculo no cliente')).toBeInTheDocument()
    expect(screen.getByText('Recebimentos, média móvel e projeção')).toBeInTheDocument()
  })
})

describe('TendenciaSection (P7 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=tendencia',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/reports/period'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=tendencia' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state sem série diária', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data: url === '/finance/reports/period' ? { ...periodo, daily: [] } : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=tendencia' })

    expect(await screen.findByRole('heading', { name: 'Sem série para analisar' })).toBeInTheDocument()
  })
})
