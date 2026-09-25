import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { SalvosSection } from '../sections/SalvosSection'
import type { SavedReport } from '../useAnalyticsData'

/** P8 — Relatórios salvos: lista/cria/remove com gate finance.write. */
const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post, delete: h.delete } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => true, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const salvos: SavedReport[] = [
  {
    id: 1,
    name: 'Fechamento setembro',
    report_type: 'dre',
    params: null,
    created_by: 'u1',
    created_at: '2026-09-24T12:00:00',
  },
]

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
  if (url === '/finance/saved-reports') return { items: salvos, total: salvos.length }
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('SalvosSection (P8 — dado)', () => {
  it('lista os relatórios salvos com o tipo legível', () => {
    renderWithProviders(
      <SalvosSection
        data={salvos}
        canWrite
        saving={false}
        onCreate={vi.fn().mockResolvedValue(true)}
        onDelete={vi.fn().mockResolvedValue(true)}
      />
    )

    expect(screen.getByText('Fechamento setembro')).toBeInTheDocument()
    expect(screen.getByText('DRE')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Novo' })).toBeInTheDocument()
  })

  it('cria um relatório pelo Dialog', async () => {
    const onCreate = vi.fn().mockResolvedValue(true)
    renderWithProviders(
      <SalvosSection data={salvos} canWrite saving={false} onCreate={onCreate} onDelete={vi.fn()} />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Novo' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Nome do relatório'), {
      target: { value: 'Meu fechamento' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Salvar' }))

    await waitFor(() => expect(onCreate).toHaveBeenCalledWith('Meu fechamento', 'visao-geral'))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('remove pelo Dialog de confirmação (sem window.confirm)', async () => {
    const onDelete = vi.fn().mockResolvedValue(true)
    renderWithProviders(
      <SalvosSection data={salvos} canWrite saving={false} onCreate={vi.fn()} onDelete={onDelete} />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Remover Fechamento setembro' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Remover relatório?' })).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remover' }))

    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(salvos[0]))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('sem finance.write esconde Novo e o botão de remover', () => {
    renderWithProviders(
      <SalvosSection
        data={salvos}
        canWrite={false}
        saving={false}
        onCreate={vi.fn()}
        onDelete={vi.fn()}
      />
    )
    expect(screen.queryByRole('button', { name: 'Novo' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Remover Fechamento setembro' })).toBeNull()
  })
})

describe('SalvosSection (P8 — estados do shell)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.post.mockResolvedValue({ data: {} })
    h.delete.mockResolvedValue({ data: {} })
  })

  it('mostra loading', () => {
    h.get.mockImplementation(() => new Promise(() => undefined))
    const { container } = renderWithProviders(<CentralFinanceiraPage />, {
      route: '/finance?secao=salvos',
    })
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', async () => {
    h.get.mockImplementation((url: string) =>
      url === '/finance/saved-reports'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: fixtureFor(url) })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=salvos' })

    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('estado vazio explicando como salvar', async () => {
    h.get.mockImplementation((url: string) =>
      Promise.resolve({
        data: url === '/finance/saved-reports' ? { items: [], total: 0 } : fixtureFor(url),
      })
    )
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance?secao=salvos' })

    expect(await screen.findByRole('heading', { name: 'Nenhum relatório salvo' })).toBeInTheDocument()
  })
})
