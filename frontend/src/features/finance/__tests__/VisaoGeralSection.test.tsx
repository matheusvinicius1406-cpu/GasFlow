import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'

/**
 * P5 — Visão Geral: render feliz, estados e as 4 escritas da tela (D2),
 * todas por Dialog (nunca `window.confirm`) e gate de permissão (V3).
 */
const h = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  hasPermission: (permission: string): boolean => permission.startsWith('finance.'),
}))

vi.mock('@/lib/api/client', () => ({
  apiClient: { get: h.get, post: h.post },
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
  previous: { total_receipts: 1300, total_expenses: 450, net_result: 850 },
  comparison: { receipts_pct: 15.4, expenses_pct: -11.1, net_pct: 29.4 },
}

const periodoVazio = {
  ...periodo,
  total_receipts: 0,
  total_expenses: 0,
  net_result: 0,
  daily: [{ date: '2026-09-24', receipts: 0, expenses: 0, net_result: 0 }],
  comparison: { receipts_pct: null, expenses_pct: null, net_pct: null },
}

const pagamento = {
  id: 3,
  order_codigo: 'PED123',
  amount: 150,
  method: 'PIX',
  status: 'PAID',
  paid_at: '2026-09-24',
  reference: null,
  idempotency_key: null,
  notes: null,
  created_at: '2026-09-24',
}

const recebivel = {
  id: 11,
  customer_codigo: 'CLI1',
  order_codigo: 'PED123',
  original_amount: 300,
  paid_amount: 180,
  remaining_amount: 120,
  due_date: '2026-09-20',
  status: 'OPEN',
  created_at: '2026-09-01',
  settled_at: null,
}

const despesa = {
  id: 7,
  description: 'Gasolina',
  amount: 90,
  category: 'FUEL',
  date: '2026-09-24',
  payment_method: null,
  notes: null,
  status: 'ACTIVE',
  created_at: '2026-09-24',
}

const movimentoCaixa = {
  id: 1,
  type: 'RECEIPT',
  amount: 150,
  description: 'Pedido PED123',
  reference_type: 'payment',
  reference_id: '3',
  balance_after: 1200,
  created_at: '2026-09-24',
}

function lista(items: unknown[]) {
  return { items, total: items.length, page: 1, page_size: 20, total_pages: 1 }
}

function fixtureFor(url: string, vazio = false): unknown {
  if (url === '/finance/reports/period') return vazio ? periodoVazio : periodo
  if (url === '/finance/cash/balance') return { balance: vazio ? 0 : 1200 }
  if (url === '/finance/budget') return { year: 2026, month: 9, items: [{ category: 'FUEL', amount: 500 }], total: 500 }
  if (url === '/finance/reports/categories') {
    return vazio
      ? { from: '2026-08-26', to: '2026-09-24', days: 30, total: 0, items: [] }
      : { from: '2026-08-26', to: '2026-09-24', days: 30, total: 400, items: [{ category: 'FUEL', total: 250, pct: 62.5 }] }
  }
  if (url === '/finance/receivables/summary') {
    return {
      generated_at: '2026-09-24T12:00:00',
      open_count: vazio ? 0 : 3,
      open_total: vazio ? 0 : 300,
      overdue_count: vazio ? 0 : 1,
      overdue_total: vazio ? 0 : 120,
      buckets: [],
    }
  }
  if (url === '/dashboard') return { financial: { today_received: vazio ? 0 : 250 } }
  if (url === '/finance/payments') return lista(vazio ? [] : [pagamento])
  if (url === '/finance/receivables') return lista(vazio ? [] : [recebivel])
  if (url === '/finance/expenses') return lista(vazio ? [] : [despesa])
  if (url === '/finance/cash') return lista(vazio ? [] : [movimentoCaixa])
  return lista([])
}

function mockGetResolvendo() {
  h.get.mockImplementation((url: string) => Promise.resolve({ data: fixtureFor(url) }))
}

function grupoTipos() {
  return screen.getByRole('group', { name: 'Tipo de movimentação' })
}

async function abrirSecao() {
  renderWithProviders(<CentralFinanceiraPage />)
  await screen.findByText('A receber')
}

describe('Visão Geral (P5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.hasPermission = () => true
    h.post.mockResolvedValue({ data: {} })
    mockGetResolvendo()
    vi.spyOn(window, 'confirm').mockImplementation(() => true)
  })

  it('renderiza KPIs, insights, meta, gráficos e a tabela de pagamentos', async () => {
    await abrirSecao()

    expect(screen.getByText('R$ 1.500,00')).toBeInTheDocument()
    expect(screen.getByText('Saldo em Caixa')).toBeInTheDocument()
    expect(screen.getByText('Meta do mês')).toBeInTheDocument()
    expect(screen.getByText('Movimentações')).toBeInTheDocument()
    expect(screen.getByText('#PED123')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Exportar CSV' })).toBeInTheDocument()
    expect(within(grupoTipos()).getByRole('button', { name: 'Pagamentos' })).toHaveAttribute('aria-pressed', 'true')
    // O período aparece no subtítulo e no cabeçalho de impressão (P9).
    expect(screen.getAllByText(/01\/09\/2026 a 24\/09\/2026/).length).toBeGreaterThan(0)
  })

  it('erro no período mostra o retry do SectionShell', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/reports/period' ? Promise.reject(new Error('boom')) : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />)

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
    expect(screen.getByText('Não foi possível carregar os dados.')).toBeInTheDocument()
  })

  it('período sem movimento mostra o empty state', async () => {
    h.get.mockImplementation((url: string) => Promise.resolve({ data: fixtureFor(url, true) }))
    renderWithProviders(<CentralFinanceiraPage />)

    expect(await screen.findByRole('heading', { name: 'Sem movimentações neste período' })).toBeInTheDocument()
  })

  it('busca na tabela usa o q do servidor (com debounce)', async () => {
    await abrirSecao()

    fireEvent.change(screen.getByLabelText('Buscar movimentações'), { target: { value: 'PED' } })

    await waitFor(
      () => {
        expect(h.get).toHaveBeenCalledWith(
          '/finance/payments',
          expect.objectContaining({ params: expect.objectContaining({ q: 'PED' }) })
        )
      },
      { timeout: 3000 }
    )
  })
})

describe('Visão Geral — gráficos', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.hasPermission = () => true
    h.post.mockResolvedValue({ data: {} })
    mockGetResolvendo()
    vi.spyOn(window, 'confirm').mockImplementation(() => true)
  })

  it('expõe os quatro gráficos com rótulo acessível (fluxo, categorias, comparativo e acumulado)', async () => {
    await abrirSecao()

    expect(screen.getByRole('img', { name: /^Entradas, saídas e resultado por dia —/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /^Despesas por categoria —/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /^Comparativo com o período anterior/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /^Resultado acumulado dia a dia —/ })).toBeInTheDocument()
  })

  it('o comparativo cita os totais do período atual e do anterior', async () => {
    await abrirSecao()

    // \s cobre o espaço não separável do Intl entre "R$" e o número.
    const comparativo = screen.getByRole('img', {
      name: /recebimentos R\$\s1\.500,00 contra R\$\s1\.300,00, despesas R\$\s400,00 contra R\$\s450,00/,
    })
    expect(comparativo).toBeInTheDocument()
  })

  it('sem período anterior mostra o texto de fallback no comparativo', async () => {
    const semAnterior = { ...periodo, previous: undefined }
    h.get.mockImplementation((url: string) =>
      Promise.resolve({ data: url === '/finance/reports/period' ? semAnterior : fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />)

    expect(await screen.findByText('Sem período anterior para comparar.')).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /^Comparativo com o período anterior/ })).toBeNull()
    // O acumulado continua de pé mesmo sem anterior.
    expect(screen.getByRole('img', { name: /^Resultado acumulado dia a dia —/ })).toBeInTheDocument()
  })
})

describe('Visão Geral — escritas (D2)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.hasPermission = () => true
    h.post.mockResolvedValue({ data: {} })
    mockGetResolvendo()
    vi.spyOn(window, 'confirm').mockImplementation(() => true)
  })

  it('cria nova despesa pelo Dialog', async () => {
    await abrirSecao()

    fireEvent.click(screen.getByRole('button', { name: 'Nova despesa' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Descrição da despesa'), {
      target: { value: 'Troca de óleo' },
    })
    fireEvent.change(within(dialog).getByLabelText('Valor da despesa em reais'), {
      target: { value: '120.50' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Registrar' }))

    await waitFor(() => {
      expect(h.post).toHaveBeenCalledWith('/finance/expenses', {
        description: 'Troca de óleo',
        amount: 120.5,
        category: 'OTHER',
      })
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(window.confirm).not.toHaveBeenCalled()
  })

  it('cancela despesa pelo Dialog (sem window.confirm)', async () => {
    await abrirSecao()

    fireEvent.click(within(grupoTipos()).getByRole('button', { name: 'Despesas' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar despesa Gasolina' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Cancelar despesa?' })).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirmar cancelamento' }))

    await waitFor(() => expect(h.post).toHaveBeenCalledWith('/finance/expenses/7/cancel'))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(window.confirm).not.toHaveBeenCalled()
    expect(await screen.findByText('Despesa cancelada')).toBeInTheDocument()
  })

  it('cancela pagamento pelo Dialog (sem window.confirm)', async () => {
    await abrirSecao()

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar pagamento do pedido PED123' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Cancelar pagamento?' })).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirmar cancelamento' }))

    await waitFor(() => expect(h.post).toHaveBeenCalledWith('/payments/3/cancel'))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(window.confirm).not.toHaveBeenCalled()
    expect(await screen.findByText('Pagamento cancelado')).toBeInTheDocument()
  })

  it('registra recebimento de recebível pelo Dialog', async () => {
    await abrirSecao()

    fireEvent.click(within(grupoTipos()).getByRole('button', { name: 'Recebíveis' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Registrar pagamento do pedido PED123' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Registrar recebimento' })).toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('Valor do recebimento em reais'), {
      target: { value: '50' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Registrar' }))

    await waitFor(() => {
      expect(h.post).toHaveBeenCalledWith(
        '/finance/orders/PED123/payments',
        expect.objectContaining({ amount: 50, method: 'PIX', idempotency_key: expect.any(String) })
      )
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByText('Recebimento registrado')).toBeInTheDocument()
  })
})

describe('Visão Geral — permissões (V3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
    mockGetResolvendo()
    vi.spyOn(window, 'confirm').mockImplementation(() => true)
  })

  it('sem finance.write/finance.receive as ações de escrita ficam ocultas', async () => {
    h.hasPermission = () => false
    await abrirSecao()

    expect(screen.queryByRole('button', { name: 'Nova despesa' })).toBeNull()

    fireEvent.click(within(grupoTipos()).getByRole('button', { name: 'Despesas' }))
    await screen.findByText('Gasolina')
    expect(screen.queryByRole('button', { name: 'Cancelar despesa Gasolina' })).toBeNull()

    fireEvent.click(within(grupoTipos()).getByRole('button', { name: 'Recebíveis' }))
    await screen.findByText('CLI1')
    expect(screen.queryByRole('button', { name: 'Registrar pagamento do pedido PED123' })).toBeNull()
  })
})
