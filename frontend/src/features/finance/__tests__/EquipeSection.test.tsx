import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { EquipeSection } from '../sections/EquipeSection'
import type { TeamData } from '../useAnalyticsData'

/** P8 — Equipe: entregas por motorista + folha SALARY + gráficos de entregas. */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post, delete: h.delete } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const equipe: TeamData = {
  days: 30,
  generated_at: '2026-09-24T12:00:00',
  by_driver: [
    { driver_id: '000001', nome: 'João', assigned: 10, delivered: 9, failed: 1, avg_minutes: 45.5 },
    { driver_id: '000002', nome: null, assigned: 4, delivered: 4, failed: 0, avg_minutes: null },
  ],
  salary_total: 2000,
  note: 'Folha soma apenas despesas SALARY do período.',
}

const entregas = { days: 30, generated_at: 'x', by_day: [], by_driver: [], by_neighborhood: [] }

const periodo = {
  from: '2026-09-01',
  to: '2026-09-24',
  days: 30,
  total_receipts: 0,
  total_expenses: 0,
  net_result: 0,
  daily: [],
  comparison: { receipts_pct: null, expenses_pct: null, net_pct: null },
}

function fixtureFor(url: string): unknown {
  if (url === '/finance/reports/team') return equipe
  if (url === '/reports/deliveries') return entregas
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('EquipeSection (P8 — dado)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.get.mockImplementation((url: string) => Promise.resolve({ data: fixtureFor(url) }))
  })

  it('mostra entregas, folha e o desempenho por motorista', async () => {
    renderWithProviders(<EquipeSection data={equipe} />)

    expect(within(screen.getByTestId('equipe-entregues')).getByText('13')).toBeInTheDocument()
    expect(within(screen.getByTestId('equipe-falhas')).getByText('1')).toBeInTheDocument()
    expect(within(screen.getByTestId('equipe-folha')).getByText('R$ 2.000,00')).toBeInTheDocument()
    expect(screen.getByText('João')).toBeInTheDocument()
    expect(screen.getByText('000002')).toBeInTheDocument()
    expect(screen.getByText(/Folha soma apenas despesas SALARY/)).toBeInTheDocument()

    // DeliveryCharts (movido no P8) vem junto da seção
    await waitFor(() => expect(screen.getByText('Entregas por dia')).toBeInTheDocument())
  })
})

describe('EquipeSection (P8 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=equipe',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/reports/team'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=equipe' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })
})
