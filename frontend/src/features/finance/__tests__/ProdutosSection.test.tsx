import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { ProdutosSection } from '../sections/ProdutosSection'
import type { ProductsData } from '../useAnalyticsData'

/**
 * P6 — Produtos: margem por produto com o rótulo honesto `cost_known`
 * (sem nota de compra → "Sem custo", nunca margem zero disfarçada).
 */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const produtos: ProductsData = {
  from: '2026-09-01',
  to: '2026-09-24',
  days: 30,
  revenue: 5000,
  items: [
    {
      product_codigo: 'P1',
      product_nome: 'Gás 13kg',
      quantity: 20,
      revenue: 3000,
      unit_cost: 100,
      cost_known: true,
      margin: 1000,
      margin_pct: 33.3,
    },
    {
      product_codigo: 'P2',
      product_nome: 'Água 20L',
      quantity: 10,
      revenue: 2000,
      unit_cost: null,
      cost_known: false,
      margin: null,
      margin_pct: null,
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
  if (url === '/finance/reports/products') return produtos
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('ProdutosSection (P6 — dado)', () => {
  it('lista a margem e marca o produto sem custo conhecido', () => {
    renderWithProviders(<ProdutosSection data={produtos} />)

    expect(within(screen.getByTestId('produtos-receita')).getByText('R$ 5.000,00')).toBeInTheDocument()
    expect(within(screen.getByTestId('produtos-margem')).getByText('R$ 1.000,00')).toBeInTheDocument()
    expect(screen.getByText('Gás 13kg')).toBeInTheDocument()
    expect(screen.getByText('Sem custo')).toBeInTheDocument()
    expect(screen.getByText('Margem incompleta')).toBeInTheDocument()
  })

  it('sem itens com custo desconhecido não mostra o aviso', () => {
    renderWithProviders(<ProdutosSection data={{ ...produtos, items: produtos.items.slice(0, 1) }} />)
    expect(screen.queryByText('Margem incompleta')).toBeNull()
  })
})

describe('ProdutosSection (P6 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=produtos',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/reports/products'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=produtos' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state sem produtos vendidos', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data: url === '/finance/reports/products' ? { ...produtos, items: [], revenue: 0 } : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=produtos' })

    expect(await screen.findByRole('heading', { name: 'Nenhum produto vendido' })).toBeInTheDocument()
  })
})
