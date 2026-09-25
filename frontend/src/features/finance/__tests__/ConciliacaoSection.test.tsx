import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { ConciliacaoSection } from '../sections/ConciliacaoSection'
import type { ConciliationData } from '../useAnalyticsData'

/** P8 — Conciliação: pagamento ↔ caixa ↔ recebível, divergências "a revisar". */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post, delete: h.delete } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const conciliacao: ConciliationData = {
  from: '2026-09-01',
  to: '2026-09-24',
  days: 30,
  checked: 10,
  matched: 8,
  to_review: 2,
  items: [
    {
      payment_id: 1,
      order_codigo: 'PED1',
      amount: 100,
      method: 'PIX',
      status: 'PAID',
      has_cash_movement: false,
      receivable_status: 'OPEN',
      receivable_delta: 0,
      issues: ['sem_recebivel'],
    },
    {
      payment_id: 2,
      order_codigo: 'PED2',
      amount: 50,
      method: 'CASH',
      status: 'PAID',
      has_cash_movement: true,
      receivable_status: 'PAID',
      receivable_delta: 50,
      issues: ['recebivel_em_divergencia'],
    },
  ],
  note: 'Divergências são "a revisar".',
}

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
  if (url === '/finance/reports/conciliation') return conciliacao
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('ConciliacaoSection (P8 — dado)', () => {
  it('mostra os totais e os itens a revisar', () => {
    renderWithProviders(<ConciliacaoSection data={conciliacao} />)

    expect(within(screen.getByTestId('conciliacao-conferidos')).getByText('10')).toBeInTheDocument()
    expect(within(screen.getByTestId('conciliacao-conciliados')).getByText('8')).toBeInTheDocument()
    expect(within(screen.getByTestId('conciliacao-revisar')).getByText('2')).toBeInTheDocument()
    expect(screen.getByText('Divergências a revisar')).toBeInTheDocument()
    expect(screen.getByText('#PED1')).toBeInTheDocument()
    expect(screen.getByText('Sem recebível')).toBeInTheDocument()
    expect(screen.getByText('Recebível em divergência')).toBeInTheDocument()
  })

  it('mostra tudo conciliado quando não há divergência', () => {
    renderWithProviders(
      <ConciliacaoSection data={{ ...conciliacao, to_review: 0, items: [] }} />
    )
    expect(screen.getByText('Tudo conciliado')).toBeInTheDocument()
    expect(screen.queryByTestId('conciliacao-tabela')).toBeNull()
  })
})

describe('ConciliacaoSection (P8 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=conciliacao',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/reports/conciliation'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=conciliacao' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state sem pagamentos no período', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data:
          url === '/finance/reports/conciliation'
            ? { ...conciliacao, checked: 0, matched: 0, to_review: 0, items: [] }
            : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=conciliacao' })

    expect(await screen.findByRole('heading', { name: 'Nada a conciliar no período' })).toBeInTheDocument()
  })
})
