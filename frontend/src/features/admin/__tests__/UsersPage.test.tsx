import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

const { mockPost, mockPatch, mockHasPermission } = vi.hoisted(() => ({
  mockPost: vi.fn<(url: string, body?: unknown) => Promise<{ data: unknown }>>(),
  mockPatch: vi.fn<(url: string, body?: unknown) => Promise<{ data: unknown }>>(),
  mockHasPermission: vi.fn<(permission: string) => boolean>(() => true),
}))

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn((url: string) => {
      if (url === '/admin/users') {
        return Promise.resolve({
          data: {
            users: [
              {
                id: 'u1',
                username: 'maria',
                email: 'maria@gasflow.local',
                display_name: 'Maria Silva',
                status: 'ACTIVE',
                role_id: 'role-op',
                must_change_password: false,
                last_login_at: '2026-09-12T10:00:00',
                created_at: null,
              },
              {
                id: 'u2',
                username: 'joao',
                email: 'joao@gasflow.local',
                display_name: 'João Souza',
                status: 'DISABLED',
                role_id: 'role-viewer',
                must_change_password: true,
                last_login_at: null,
                created_at: null,
              },
            ],
          },
        })
      }
      if (url === '/admin/roles') {
        return Promise.resolve({
          data: {
            roles: [
              { id: 'role-op', name: 'OPERATOR', system_role: 'OPERATOR', permissions: [] },
              { id: 'role-viewer', name: 'VIEWER', system_role: 'VIEWER', permissions: [] },
            ],
          },
        })
      }
      return Promise.resolve({ data: {} })
    }),
    post: mockPost,
    patch: mockPatch,
  },
}))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    hasPermission: (p: string) => mockHasPermission(p),
  }),
}))

import { UsersPage } from '../UsersPage'

function renderPage() {
  return render(
    <MemoryRouter>
      <UsersPage />
    </MemoryRouter>
  )
}

describe('UsersPage', () => {
  beforeEach(() => {
    mockPost.mockClear().mockResolvedValue({ data: {} })
    mockPatch.mockClear().mockResolvedValue({ data: {} })
    mockHasPermission.mockClear().mockReturnValue(true)
  })

  it('renderiza a lista de usuários', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('Maria Silva')).toBeInTheDocument()
      expect(screen.getByText('João Souza')).toBeInTheDocument()
    })
    expect(screen.getByText('2 de 2 usuários')).toBeInTheDocument()
  })

  it('filtra por busca', async () => {
    renderPage()
    await waitFor(() => screen.getByText('Maria Silva'))
    fireEvent.change(screen.getByLabelText('Buscar usuários'), { target: { value: 'maria' } })
    expect(screen.getByText('Maria Silva')).toBeInTheDocument()
    expect(screen.queryByText('João Souza')).not.toBeInTheDocument()
    expect(screen.getByText('1 de 2 usuários')).toBeInTheDocument()
  })

  it('filtra por status', async () => {
    renderPage()
    await waitFor(() => screen.getByText('Maria Silva'))
    fireEvent.change(screen.getByLabelText('Filtrar por status'), {
      target: { value: 'DISABLED' },
    })
    expect(screen.queryByText('Maria Silva')).not.toBeInTheDocument()
    expect(screen.getByText('João Souza')).toBeInTheDocument()
  })

  it('esconde ações sem permissão', async () => {
    mockHasPermission.mockImplementation(
      (p: string) => p === 'user.read' // só leitura
    )
    renderPage()
    await waitFor(() => screen.getByText('Maria Silva'))
    expect(screen.queryByRole('button', { name: /Novo usuário/ })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Editar maria')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Resetar senha de maria')).not.toBeInTheDocument()
  })

  it('abre modal de criação e chama POST /admin/users', async () => {
    renderPage()
    await waitFor(() => screen.getByText('Maria Silva'))
    fireEvent.click(screen.getByRole('button', { name: /Novo usuário/ }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText('Usuário'), { target: { value: 'novo_user' } })
    fireEvent.change(within(dialog).getByLabelText('E-mail'), { target: { value: 'novo@gasflow.local' } })
    fireEvent.change(within(dialog).getByPlaceholderText('mínimo 6 caracteres'), {
      target: { value: 'SenhaForte1' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Salvar' }))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/admin/users', expect.objectContaining({ username: 'novo_user' }))
    })
  })

  it('reset mostra senha temporária uma única vez', async () => {
    mockPost.mockResolvedValue({ data: { temporary_password: 'ABCD-EFGH-JKLM', success: true } })
    renderPage()
    await waitFor(() => screen.getByText('Maria Silva'))
    fireEvent.click(screen.getByLabelText('Resetar senha de maria'))
    fireEvent.click(screen.getByRole('button', { name: 'Gerar senha temporária' }))

    await waitFor(() => {
      expect(screen.getByText('ABCD-EFGH-JKLM')).toBeInTheDocument()
    })
    expect(mockPost).toHaveBeenCalledWith('/admin/users/u1/reset-password')
  })

  it('toggle desativa usuário ativo', async () => {
    renderPage()
    await waitFor(() => screen.getByText('Maria Silva'))
    const buttons = screen.getAllByRole('button', { name: 'Desativar' })
    fireEvent.click(buttons[0]!)
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/admin/users/u1/deactivate')
    })
  })
})
