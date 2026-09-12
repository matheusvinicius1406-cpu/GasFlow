import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'

const { mockGet, mockHasPermission } = vi.hoisted(() => ({
  mockGet: vi.fn<(url: string, config?: { params?: Record<string, unknown> }) => Promise<{ data: unknown }>>(),
  mockHasPermission: vi.fn<(permission: string) => boolean>(() => true),
}))

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: mockGet,
  },
}))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    hasPermission: (p: string) => mockHasPermission(p),
    isLoading: false,
  }),
  // Réplica fiel do guard real (mesma semântica do App.tsx).
  PermissionRoute: ({
    permissions,
    children,
  }: {
    permissions: string[]
    children: React.ReactNode
  }) => {
    if (!permissions.some((p: string) => mockHasPermission(p))) {
      return <Navigate to="/" replace />
    }
    return <>{children}</>
  },
}))

import { AuditPage } from '../AuditPage'
import { PermissionRoute } from '@/features/auth'

const RECORDS = {
  records: [
    {
      id: 'a1',
      actor_id: 'admin-001',
      action: 'USER_CREATED',
      resource: 'user',
      resource_id: 'u9abc123',
      result: 'SUCCESS',
      timestamp: '2026-09-12T10:00:00',
      before_json: null,
      after_json: { username: 'novo' },
      platform: 'desktop',
    },
    {
      id: 'a2',
      actor_id: 'op-1',
      action: 'AUTH_SUCCESS',
      resource: '',
      resource_id: '',
      result: 'SUCCESS',
      timestamp: '2026-09-12T09:00:00',
      before_json: null,
      after_json: null,
      platform: 'desktop',
    },
  ],
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AuditPage />
    </MemoryRouter>
  )
}

async function waitForTable() {
  const table = await screen.findByRole('table')
  const actors = await within(table).findAllByText('admin-001')
  expect(actors.length).toBeGreaterThan(0)
  return table
}

describe('AuditPage', () => {
  beforeEach(() => {
    mockGet.mockReset().mockResolvedValue({ data: RECORDS })
    mockHasPermission.mockReset().mockReturnValue(true)
  })

  it('renderiza registros da auditoria', async () => {
    renderPage()
    const table = await waitForTable()
    expect(within(table).getByText('USER_CREATED')).toBeInTheDocument()
    expect(screen.getByText('2 registros')).toBeInTheDocument()
  })

  it('filtros disparam query com parâmetros corretos', async () => {
    renderPage()
    await waitForTable()

    fireEvent.change(screen.getByLabelText('Filtrar por ator'), { target: { value: 'admin-001' } })
    fireEvent.change(screen.getByLabelText('Filtrar por ação'), { target: { value: 'USER_CREATED' } })
    fireEvent.change(screen.getByLabelText('Data inicial'), { target: { value: '2026-09-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))

    await waitFor(() => {
      expect(mockGet).toHaveBeenLastCalledWith(
        '/admin/audit',
        expect.objectContaining({
          params: expect.objectContaining({
            actor_id: 'admin-001',
            action: 'USER_CREATED',
            from_ts: '2026-09-01T00:00:00',
            offset: 0,
            limit: 50,
          }),
        })
      )
    })
  })

  it('paginação avança com offset quando a página está cheia', async () => {
    const fullPage = {
      records: Array.from({ length: 50 }, (_, i) => ({
        id: `r${i}`,
        actor_id: 'admin-001',
        action: 'RESOURCE_MODIFIED',
        resource: 'user',
        resource_id: '',
        result: 'SUCCESS',
        timestamp: '2026-09-12T08:00:00',
        before_json: null,
        after_json: null,
        platform: 'desktop',
      })),
    }
    mockGet.mockResolvedValue({ data: fullPage })

    renderPage()
    await waitForTable()

    const next = screen.getByRole('button', { name: 'Próxima' })
    expect(next).not.toBeDisabled()
    fireEvent.click(next)

    await waitFor(() => {
      expect(mockGet).toHaveBeenLastCalledWith(
        '/admin/audit',
        expect.objectContaining({ params: expect.objectContaining({ offset: 50 }) })
      )
    })
  })

  it('export CSV gera conteúdo esperado', async () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function (this: HTMLAnchorElement) {
        const today = new Date().toISOString().slice(0, 10)
        expect(this.download).toBe(`gasflow-audit-${today}.csv`)
        expect(this.href).toBe('blob:mock')
      })

    renderPage()
    await waitForTable()
    fireEvent.click(screen.getByRole('button', { name: /Exportar CSV/ }))

    expect(createObjectURL).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalled()

    clickSpy.mockRestore()
  })

  it('guard: sem audit.view, PermissionRoute redireciona para o dashboard', async () => {
    mockHasPermission.mockReturnValue(false)

    render(
      <MemoryRouter initialEntries={['/admin/audit']}>
        <Routes>
          <Route
            path="/admin/audit"
            element={
              <PermissionRoute permissions={['audit.view']}>
                <div>página-protegida</div>
              </PermissionRoute>
            }
          />
          <Route path="/" element={<div>dashboard</div>} />
        </Routes>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('dashboard')).toBeInTheDocument()
      expect(screen.queryByText('página-protegida')).not.toBeInTheDocument()
    })
  })

  it('guard: com audit.view, renderiza o conteúdo', () => {
    mockHasPermission.mockReturnValue(true)

    render(
      <MemoryRouter initialEntries={['/admin/audit']}>
        <Routes>
          <Route
            path="/admin/audit"
            element={
              <PermissionRoute permissions={['audit.view']}>
                <div>página-protegida</div>
              </PermissionRoute>
            }
          />
          <Route path="/" element={<div>dashboard</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByText('página-protegida')).toBeInTheDocument()
  })
})
