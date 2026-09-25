import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { AuditoriaSection } from '../sections/AuditoriaSection'
import type { AuditData } from '../useAnalyticsData'

/** P8 — Auditoria: trilha sem backfill, oculta sem `audit.view`. */
const h = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
  hasPermission: (() => true) as (permission: string) => boolean,
}))

vi.mock('@/lib/api/client', () => ({ apiClient: { get: h.get, post: h.post, delete: h.delete } }))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: h.hasPermission, isLoading: false }),
  PermissionRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children as React.ReactElement,
}))

const auditoria: AuditData = {
  days: 30,
  total: 1,
  items: [
    {
      id: '1',
      actor_id: 'u1',
      action: 'budget.upserted',
      resource: 'budget',
      resource_id: '2026-09',
      result: 'success',
      timestamp: '2026-09-24T12:00:00',
      before_json: null,
      after_json: null,
      details: null,
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
  comparison: { receipts_pct: null, expenses_pct: null, net_pct: null },
}

function fixtureFor(url: string): unknown {
  if (url === '/finance/audit') return auditoria
  if (url === '/finance/reports/period') return periodo
  if (url === '/finance/cash/balance') return { balance: 1200 }
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
}

describe('AuditoriaSection (P8 — dado)', () => {
  it('lista a trilha com recurso e ação', () => {
    renderWithProviders(<AuditoriaSection data={auditoria} />)

    expect(screen.getByText('Trilha sem backfill')).toBeInTheDocument()
    expect(screen.getByText('budget.upserted')).toBeInTheDocument()
    expect(screen.getByText('Orçamento')).toBeInTheDocument()
    expect(within(screen.getByTestId('auditoria-tabela')).getByText('success')).toBeInTheDocument()
  })
})

describe('AuditoriaSection (P8 — gate audit.view)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.hasPermission = () => true
    h.post.mockResolvedValue({ data: {} })
  })

  it('com audit.view a seção carrega a trilha', async () => {
    h.get.mockImplementation((url: string) => Promise.resolve({ data: fixtureFor(url) }))
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance/central?secao=auditoria' })

    expect(await screen.findByText('budget.upserted')).toBeInTheDocument()
  })

  it('sem audit.view a aba some e o deep-link mostra "Sem permissão"', async () => {
    h.hasPermission = (permission: string) => permission !== 'audit.view'
    h.get.mockImplementation((url: string) => Promise.resolve({ data: fixtureFor(url) }))

    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance/central?secao=auditoria' })

    const abas = screen.getByRole('group', { name: 'Seções da Central Financeira' })
    expect(within(abas).queryByRole('button', { name: 'Auditoria' })).toBeNull()
    expect(await screen.findByRole('heading', { name: 'Sem permissão' })).toBeInTheDocument()
    expect(h.get).not.toHaveBeenCalledWith('/finance/audit', expect.anything())
  })
})
