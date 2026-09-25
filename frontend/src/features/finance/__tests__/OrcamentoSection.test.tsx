import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { OrcamentoSection } from '../sections/OrcamentoSection'
import type { BudgetSectionData } from '../useAnalyticsData'

/**
 * P6 — Orçamento (V4): meta mensal por categoria contra o realizado do
 * período, com edição via Dialog (PUT replace-all) e gate `finance.write`.
 */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post, put: h.put } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const orcamento: BudgetSectionData = {
  budget: {
    year: 2026,
    month: 9,
    items: [
      { category: 'FUEL', amount: 1000 },
      { category: 'MAINTENANCE', amount: 500 },
    ],
    total: 1500,
  },
  realized: {
    from: '2026-08-26',
    to: '2026-09-24',
    days: 30,
    total: 1100,
    items: [
      { category: 'FUEL', total: 900, pct: 81.8 },
      { category: 'SUPPLIES', total: 200, pct: 18.2 },
    ],
  },
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
  if (url === '/finance/budget') return orcamento.budget
  if (url === '/finance/reports/categories') return orcamento.realized
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('OrcamentoSection (P6/V4 — dado)', () => {
  it('compara meta e realizado por categoria, marcando quem não tem meta', () => {
    renderWithProviders(
      <OrcamentoSection
        data={orcamento}
        days={30}
        canWrite
        saving={false}
        onSave={vi.fn().mockResolvedValue(true)}
      />
    )

    expect(within(screen.getByTestId('orcamento-meta')).getByText('R$ 1.500,00')).toBeInTheDocument()
    expect(
      within(screen.getByTestId('orcamento-realizado')).getByText('R$ 1.100,00')
    ).toBeInTheDocument()
    expect(within(screen.getByTestId('orcamento-saldo')).getByText('R$ 400,00')).toBeInTheDocument()
    expect(screen.getByText('Suprimentos')).toBeInTheDocument()
    expect(screen.getByText('sem meta')).toBeInTheDocument()
  })

  it('avisa que a meta é mensal quando o período não é de 30 dias', () => {
    renderWithProviders(
      <OrcamentoSection
        data={orcamento}
        days={7}
        canWrite={false}
        saving={false}
        onSave={vi.fn().mockResolvedValue(true)}
      />
    )
    expect(screen.getByText('Meta = mês corrente')).toBeInTheDocument()
  })

  it('sem finance.write não mostra o botão de editar', () => {
    renderWithProviders(
      <OrcamentoSection
        data={orcamento}
        days={30}
        canWrite={false}
        saving={false}
        onSave={vi.fn().mockResolvedValue(true)}
      />
    )
    expect(screen.queryByRole('button', { name: 'Editar orçamento' })).toBeNull()
  })

  it('salva o mês via Dialog (PUT replace-all) e fecha', async () => {
    const onSave = vi.fn().mockResolvedValue(true)
    renderWithProviders(
      <OrcamentoSection data={orcamento} days={30} canWrite saving={false} onSave={onSave} />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Editar orçamento' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Meta de Combustível'), { target: { value: '1200' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Salvar orçamento' }))

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(2026, 9, [
        { category: 'FUEL', amount: 1200 },
        { category: 'MAINTENANCE', amount: 500 },
      ])
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('permite adicionar uma categoria nova ao orçamento', async () => {
    renderWithProviders(
      <OrcamentoSection
        data={orcamento}
        days={30}
        canWrite
        saving={false}
        onSave={vi.fn().mockResolvedValue(true)}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Editar orçamento' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Categoria para adicionar'), {
      target: { value: 'SUPPLIES' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Adicionar' }))

    expect(within(dialog).getByLabelText('Meta de Suprimentos')).toBeInTheDocument()
  })
})

describe('OrcamentoSection (P6 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
    h.put.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=orcamento',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/budget'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=orcamento' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state sem orçamento nem despesas', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data:
          url === '/finance/budget'
            ? { year: 2026, month: 9, items: [], total: 0 }
            : url === '/finance/reports/categories'
              ? { from: '2026-08-26', to: '2026-09-24', days: 30, total: 0, items: [] }
              : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=orcamento' })

    expect(
      await screen.findByRole('heading', { name: 'Sem orçamento nem despesas' })
    ).toBeInTheDocument()
  })
})
