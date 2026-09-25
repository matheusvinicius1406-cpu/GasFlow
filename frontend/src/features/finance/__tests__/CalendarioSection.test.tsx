import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { CalendarioSection } from '../sections/CalendarioSection'
import type { CalendarioData } from '../useAnalyticsData'

/** P7 — Calendário: heatmap por dia + recebimentos por hora. */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const calendario: CalendarioData = {
  period: {
    from: '2026-09-23',
    to: '2026-09-24',
    days: 2,
    total_receipts: 1500,
    total_expenses: 0,
    net_result: 1500,
    daily: [
      { date: '2026-09-23', receipts: 1000, expenses: 0, net_result: 1000 },
      { date: '2026-09-24', receipts: 500, expenses: 0, net_result: 500 },
    ],
    comparison: { receipts_pct: null, expenses_pct: null, net_pct: null },
  },
  hourly: {
    from: '2026-09-23',
    to: '2026-09-24',
    days: 2,
    total: 1500,
    buckets: [
      { hour: 9, count: 1, total: 1000 },
      { hour: 14, count: 1, total: 500 },
    ],
  },
}

function fixtureFor(url: string): unknown {
  if (url === '/finance/reports/period') return calendario.period
  if (url === '/finance/reports/hourly') return calendario.hourly
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('CalendarioSection (P7 — dado)', () => {
  it('desenha o heatmap por dia e por hora', () => {
    renderWithProviders(<CalendarioSection data={calendario} />)

    expect(screen.getByText('Recebimentos por dia')).toBeInTheDocument()
    expect(screen.getByText('Recebimentos por hora')).toBeInTheDocument()
    expect(screen.getByTitle('24/09/2026 · R$ 500,00')).toBeInTheDocument()
    expect(screen.getByTitle('09h · 1 recebimento · R$ 1.000,00')).toBeInTheDocument()
    expect(screen.getByText(/R\$ 1\.500,00 em 2 recebimentos/)).toBeInTheDocument()
  })
})

describe('CalendarioSection (P7 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=calendario',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/reports/hourly'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=calendario' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state sem dias no período', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data:
          url === '/finance/reports/period'
            ? { ...calendario.period, daily: [] }
            : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=calendario' })

    expect(await screen.findByRole('heading', { name: 'Sem dias no período' })).toBeInTheDocument()
  })
})
