import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider, ProtectedRoute } from './AuthProvider'

// AuthProvider real + API mockada: valida o wiring completo (login/me → flag → gate).
const { mockMe, mockChangePasswordApi, mockLogoutApi } = vi.hoisted(() => ({
  mockMe: vi.fn<() => Promise<{ data: unknown }>>(),
  mockChangePasswordApi: vi.fn<(url: string, body?: unknown) => Promise<{ data: unknown }>>(),
  mockLogoutApi: vi.fn<(url: string) => Promise<{ data: unknown }>>(),
}))

vi.mock('@/lib/api/client', () => ({
  api: {
    auth: {
      login: vi.fn(),
      logout: mockLogoutApi,
      me: mockMe,
      changePassword: mockChangePasswordApi,
    },
  },
}))

const ME_WITH_FLAG = {
  id: 'u1',
  username: 'maria',
  email: 'maria@gasflow.local',
  display_name: 'Maria Silva',
  role: 'OPERATOR',
  permissions: [],
  must_change_password: true,
}

function renderProtected() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ProtectedRoute>
          <div>APP_PRIVADO</div>
        </ProtectedRoute>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Enforce must_change_password (P0 3.8)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('gasflow_token', 'fake-token')
    mockMe.mockResolvedValue({ data: ME_WITH_FLAG })
  })

  it('bloqueia o app e renderiza o gate quando /auth/me retorna a flag', async () => {
    renderProtected()

    expect(await screen.findByText('Troca de senha obrigatória')).toBeInTheDocument()
    expect(screen.queryByText('APP_PRIVADO')).not.toBeInTheDocument()
  })

  it('gate exige senha atual, nova e confirmação', async () => {
    renderProtected()
    await screen.findByText('Troca de senha obrigatória')

    expect(screen.getByLabelText('Senha atual')).toBeInTheDocument()
    expect(screen.getByLabelText('Nova senha')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirmar nova senha')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Salvar nova senha' })).toBeInTheDocument()
  })

  it('recusa nova senha sem maiúscula (política igual à do backend)', async () => {
    renderProtected()
    await screen.findByText('Troca de senha obrigatória')

    fireEvent.change(screen.getByLabelText('Senha atual'), { target: { value: 'Temp1234' } })
    fireEvent.change(screen.getByLabelText('Nova senha'), { target: { value: 'fraca1234' } })
    fireEvent.change(screen.getByLabelText('Confirmar nova senha'), { target: { value: 'fraca1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar nova senha' }))

    expect(
      await screen.findByText('A nova senha deve conter letra maiúscula, minúscula e número'),
    ).toBeInTheDocument()
    expect(mockChangePasswordApi).not.toHaveBeenCalled()
  })

  it('recusa quando as senhas não coincidem', async () => {
    renderProtected()
    await screen.findByText('Troca de senha obrigatória')

    fireEvent.change(screen.getByLabelText('Senha atual'), { target: { value: 'Temp1234' } })
    fireEvent.change(screen.getByLabelText('Nova senha'), { target: { value: 'NovaSenha123' } })
    fireEvent.change(screen.getByLabelText('Confirmar nova senha'), { target: { value: 'Outra1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar nova senha' }))

    expect(await screen.findByText('As senhas não coincidem')).toBeInTheDocument()
    expect(mockChangePasswordApi).not.toHaveBeenCalled()
  })

  it('troca com senha válida → POST /auth/change-password e app desbloqueia', async () => {
    mockChangePasswordApi.mockResolvedValue({ data: { success: true } })
    renderProtected()
    await screen.findByText('Troca de senha obrigatória')

    fireEvent.change(screen.getByLabelText('Senha atual'), { target: { value: 'Temp1234' } })
    fireEvent.change(screen.getByLabelText('Nova senha'), { target: { value: 'NovaSenha123' } })
    fireEvent.change(screen.getByLabelText('Confirmar nova senha'), { target: { value: 'NovaSenha123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar nova senha' }))

    await waitFor(() => {
      expect(mockChangePasswordApi).toHaveBeenCalledWith('Temp1234', 'NovaSenha123')
    })
    // Flag limpa no contexto → ProtectedRoute libera o app sem novo login.
    expect(await screen.findByText('APP_PRIVADO')).toBeInTheDocument()
    expect(screen.queryByText('Troca de senha obrigatória')).not.toBeInTheDocument()
  })

  it('propaga erro do backend (senha atual incorreta → 403) e segue bloqueado', async () => {
    mockChangePasswordApi.mockRejectedValue({
      response: { status: 403, data: { detail: 'Current password is incorrect' } },
    })
    renderProtected()
    await screen.findByText('Troca de senha obrigatória')

    fireEvent.change(screen.getByLabelText('Senha atual'), { target: { value: 'Errada123' } })
    fireEvent.change(screen.getByLabelText('Nova senha'), { target: { value: 'NovaSenha123' } })
    fireEvent.change(screen.getByLabelText('Confirmar nova senha'), { target: { value: 'NovaSenha123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar nova senha' }))

    expect(await screen.findByText('Current password is incorrect')).toBeInTheDocument()
    expect(screen.queryByText('APP_PRIVADO')).not.toBeInTheDocument()
  })

  it('gate oferece saída via logout ("Entrar com outra conta")', async () => {
    mockLogoutApi.mockResolvedValue({ data: { success: true } })
    renderProtected()
    await screen.findByText('Troca de senha obrigatória')

    fireEvent.click(screen.getByText('Entrar com outra conta'))
    expect(mockLogoutApi).toHaveBeenCalledTimes(1)
  })
})
