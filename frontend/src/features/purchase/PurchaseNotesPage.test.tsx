import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'

const {
  mockList,
  mockGet,
  mockCreate,
  mockUpdate,
  mockConfirm,
  mockCancel,
  mockProducts,
  mockHasPermission,
} = vi.hoisted(() => ({
  mockList: vi.fn<() => Promise<{ data: unknown }>>(),
  mockGet: vi.fn<() => Promise<{ data: unknown }>>(),
  mockCreate: vi.fn<(data: unknown) => Promise<{ data: unknown }>>(),
  mockUpdate: vi.fn<(id: string, data: unknown) => Promise<{ data: unknown }>>(),
  mockConfirm: vi.fn<(id: string) => Promise<{ data: unknown }>>(),
  mockCancel: vi.fn<(id: string) => Promise<{ data: unknown }>>(),
  mockProducts: vi.fn<() => Promise<{ data: unknown }>>(),
  mockHasPermission: vi.fn<(permission: string) => boolean>(() => true),
}))

vi.mock('@/lib/api/client', () => ({
  api: {
    purchaseNotes: {
      list: mockList,
      get: mockGet,
      create: mockCreate,
      update: mockUpdate,
      confirm: mockConfirm,
      cancel: mockCancel,
    },
    products: { list: mockProducts },
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

import { PurchaseNotesPage } from './PurchaseNotesPage'
import { PermissionRoute } from '@/features/auth'

const NOTE = {
  id: 'note-1',
  note_number: 1,
  supplier_name: 'Marcos Gás LTDA',
  supplier_cnpj: '12.345.678/0001-90',
  issue_date: '2026-09-14',
  total_cents: 80000,
  observations: 'compra do dia',
  status: 'DRAFT',
  created_at: '2026-09-14T10:00:00',
  items: [
    {
      product_codigo: 'P13',
      product_name: 'GLP 13kg',
      quantity: 2,
      unit_price_cents: 40000,
      subtotal_cents: 80000,
    },
  ],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/purchase-notes']}>
      <Routes>
        <Route
          path="/purchase-notes"
          element={
            <PermissionRoute permissions={['purchase.read']}>
              <PurchaseNotesPage />
            </PermissionRoute>
          }
        />
        <Route path="/" element={<div>Dashboard</div>} />
      </Routes>
    </MemoryRouter>
  )
}

async function waitForTable() {
  const table = await screen.findByRole('table')
  await waitFor(() => {
    expect(screen.getByText('Marcos Gás LTDA')).toBeInTheDocument()
  })
  return table
}

describe('PurchaseNotesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockList.mockResolvedValue({ data: { notes: [NOTE] } })
    mockGet.mockResolvedValue({ data: NOTE })
    mockProducts.mockResolvedValue({
      data: { products: [{ codigo: 'P13', nome: 'GLP 13kg' }] },
    })
    mockHasPermission.mockReturnValue(true)
  })

  it('1. lista renderiza notas com status e total', async () => {
    renderPage()
    const table = await waitForTable()
    expect(table).toBeInTheDocument()
    expect(screen.getByText('#1')).toBeInTheDocument()
    expect(screen.getByText('R$ 800,00')).toBeInTheDocument()
    // status via badge (o <option> do filtro tem o mesmo texto)
    expect(screen.getAllByText('Rascunho').length).toBeGreaterThanOrEqual(1)
  })

  it('2. form valida campos obrigatórios (fornecedor e item)', async () => {
    renderPage()
    await waitForTable()

    fireEvent.click(screen.getByRole('button', { name: /nova nota/i }))
    // fornecedor vazio → erro
    fireEvent.click(screen.getByRole('button', { name: /criar rascunho/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Nome do fornecedor é obrigatório.')

    // fornecedor preenchido, item sem produto → erro
    fireEvent.change(screen.getByLabelText('Fornecedor *'), { target: { value: 'Marcos Gás' } })
    fireEvent.click(screen.getByRole('button', { name: /criar rascunho/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Selecione o produto de cada item.')
    expect(mockCreate).not.toHaveBeenCalled()
  })

  it('3. submit cria DRAFT via API', async () => {
    mockCreate.mockResolvedValue({ data: { ...NOTE, id: 'note-2', note_number: 2 } })
    renderPage()
    await waitForTable()

    fireEvent.click(screen.getByRole('button', { name: /nova nota/i }))
    fireEvent.change(screen.getByLabelText('Fornecedor *'), { target: { value: 'Marcos Gás' } })
    fireEvent.change(screen.getByLabelText('Quantidade', { selector: 'input' }), {
      target: { value: '2' },
    })
    fireEvent.change(screen.getByLabelText('Preço unitário', { selector: 'input' }), {
      target: { value: '400' },
    })
    // aguarda produtos carregarem antes de selecionar (load async no useEffect)
    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'GLP 13kg (P13)' })).toBeInTheDocument()
    })
    fireEvent.change(screen.getByLabelText('Produto'), { target: { value: 'P13' } })

    fireEvent.click(screen.getByRole('button', { name: /criar rascunho/i }))
    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          supplier_name: 'Marcos Gás',
          items: [{ product_codigo: 'P13', quantity: 2, unit_price: 400 }],
        })
      )
    })
    // se validação falhar, o alert aparece e o create não é chamado
    const alert = screen.queryByRole('alert')
    expect(alert == null || !/obrigatório|Selecione|Quantidade|Preço/.test(alert.textContent ?? '')).toBe(true)
  })

  it('4. confirmar dispara API e recarrega lista', async () => {
    mockConfirm.mockResolvedValue({ data: { ...NOTE, status: 'CONFIRMED' } })
    renderPage()
    await waitForTable()

    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    await waitFor(() => {
      expect(mockConfirm).toHaveBeenCalledWith('note-1')
    })
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledTimes(2) // inicial + reload pós-confirmação
    })
  })

  it('5. guard: sem purchase.read, PermissionRoute redireciona', async () => {
    mockHasPermission.mockImplementation((p: string) => p !== 'purchase.read')
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
    })
    expect(screen.queryByText('Notas de Compra')).not.toBeInTheDocument()
  })
})
