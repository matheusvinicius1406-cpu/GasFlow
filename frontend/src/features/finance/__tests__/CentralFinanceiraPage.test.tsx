import { fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { SectionShell } from '../SectionShell'
import { SECTIONS } from '../usePeriodFilter'

/**
 * P4–P8: o shell busca os dados da seção ativa e injeta. Por padrão o mock
 * de GET fica pendurado (nunca resolve) — assim os testes de estrutura não
 * dependem do fetch; quem precisa de conteúdo resolve os fixtures no teste.
 * Depois do P8 todas as 15 seções são reais.
 */
const h = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
  hasPermission: (() => true) as (permission: string) => boolean,
}))

vi.mock('@/lib/api/client', () => ({
  apiClient: { get: h.get, post: h.post, delete: h.delete },
}))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: h.hasPermission, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const periodo = {
  from: '2026-09-01',
  to: '2026-09-24',
  days: 30,
  total_receipts: 1500,
  total_expenses: 400,
  net_result: 1100,
  daily: [
    { date: '2026-09-23', receipts: 500, expenses: 100, net_result: 400 },
    { date: '2026-09-24', receipts: 1000, expenses: 300, net_result: 700 },
  ],
  previous: { from: '2026-08-01', to: '2026-08-31', total_receipts: 1300, total_expenses: 450, net_result: 850 },
  comparison: { receipts_pct: 15.4, expenses_pct: -11.1, net_pct: 29.4 },
}

const dre = {
  from: '2026-09-01',
  to: '2026-09-24',
  days: 30,
  revenue: 1000,
  cmv: 400,
  gross_profit: 600,
  expenses: 200,
  result: 400,
  cmv_coverage: 100,
  expense_items: [],
}

const heatmap = {
  period_days: 30,
  generated_at: '2026-09-24T12:00:00',
  cached: false,
  total: 5,
  neighborhoods: [{ neighborhood: 'Centro', count: 5, center: { lat: -30.03, lng: -51.22 } }],
}

function fixtureFor(url: string): unknown {
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/reports/dre') return dre
  if (url === '/finance/cash/balance') return { balance: 1200 }
  if (url === '/finance/budget') return { year: 2026, month: 9, items: [], total: 0 }
  if (url === '/finance/reports/categories') return { from: '2026-08-26', to: '2026-09-24', days: 30, total: 0, items: [] }
  if (url === '/finance/receivables/summary') {
    return { generated_at: '2026-09-24T12:00:00', open_count: 0, open_total: 0, overdue_count: 0, overdue_total: 0, buckets: [] }
  }
  if (url === '/dashboard') return { financial: { today_received: 0 } }
  if (url === '/reports/heatmap') return heatmap
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

function abaGroup() {
  return screen.getByRole('group', { name: 'Seções da Central Financeira' })
}

function presetGroup() {
  return screen.getByRole('group', { name: 'Período da Central Financeira' })
}

describe('CentralFinanceiraPage (P4–P8 — shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.hasPermission = () => true
    h.get.mockImplementation(() => new Promise(() => undefined))
    h.post.mockResolvedValue({ data: {} })
  })

  it('renderiza título e as 15 abas das seções', () => {
    renderWithProviders(<CentralFinanceiraPage />)
    expect(screen.getByRole('heading', { name: 'Central Financeira' })).toBeInTheDocument()
    expect(within(abaGroup()).getAllByRole('button')).toHaveLength(SECTIONS.length)
    expect(SECTIONS).toHaveLength(15)
  })

  it('presets V1 (Hoje/7/30/90/180) com 30 dias ativo por padrão', () => {
    renderWithProviders(<CentralFinanceiraPage />)
    const grupo = presetGroup()
    for (const nome of ['Hoje', '7 dias', '30 dias', '90 dias', '180 dias']) {
      expect(within(grupo).getByRole('button', { name: nome })).toBeInTheDocument()
    }
    expect(within(grupo).getByRole('button', { name: '30 dias' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(grupo).getByRole('button', { name: '180 dias' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('trocar o preset marca o novo período', () => {
    renderWithProviders(<CentralFinanceiraPage />)
    fireEvent.click(within(presetGroup()).getByRole('button', { name: '180 dias' }))
    expect(within(presetGroup()).getByRole('button', { name: '180 dias' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(presetGroup()).getByRole('button', { name: '30 dias' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('aba padrão é a Visão Geral real (P5) e trocar de aba muda a seção', async () => {
    h.get.mockImplementation((url: string) => Promise.resolve({ data: fixtureFor(url) }))
    renderWithProviders(<CentralFinanceiraPage />)

    expect(await screen.findByText('A receber')).toBeInTheDocument()
    expect(screen.getByText('Saldo em Caixa')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Exportar CSV' })).toBeInTheDocument()

    // Depois do P8 todas as seções são reais — a aba DRE rende a seção de verdade.
    fireEvent.click(within(abaGroup()).getByRole('button', { name: 'DRE' }))
    expect(await screen.findByTestId('dre-receita')).toBeInTheDocument()
    expect(screen.queryByText(/em construção/)).toBeNull()
  })

  it('respeita o deep-link ?secao=', async () => {
    h.get.mockImplementation((url: string) => Promise.resolve({ data: fixtureFor(url) }))
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance/central?secao=mapa-de-calor' })

    expect(await screen.findByText(/5 entrega\(s\) em 30 dias/)).toBeInTheDocument()
    expect(within(abaGroup()).getByRole('button', { name: 'Mapa de Calor' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('seção desconhecida na URL cai na padrão (visao-geral)', () => {
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance/central?secao=inexistente',
    })
    expect(within(abaGroup()).getByRole('button', { name: 'Visão Geral' })).toHaveAttribute('aria-pressed', 'true')
    // Dados pendurados → a seção real fica no loading do SectionShell.
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })
})

describe('SectionShell', () => {
  it('mostra loading', () => {
    const { container } = renderWithProviders(<SectionShell title="T" loading />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', () => {
    renderWithProviders(<SectionShell title="T" error onRetry={() => {}} />)
    expect(screen.getByText('Não foi possível carregar os dados.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state', () => {
    renderWithProviders(<SectionShell title="T" empty emptyTitle="Vazio aqui" emptyDescription="Nada." />)
    expect(screen.getByRole('heading', { name: 'Vazio aqui' })).toBeInTheDocument()
    expect(screen.getByText('Nada.')).toBeInTheDocument()
  })
})
