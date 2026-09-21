import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

const { loginMock } = vi.hoisted(() => ({ loginMock: vi.fn() }))

vi.mock('./AuthProvider', () => ({
  useAuth: () => ({
    login: loginMock,
    logout: vi.fn(),
    isAuthenticated: false,
    tenantId: null,
  }),
}))

import { LoginPage } from './LoginPage'

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the login form', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByText('GasFlow')).toBeInTheDocument()
    expect(screen.getByLabelText('Usuário')).toBeInTheDocument()
    expect(screen.getByLabelText('Senha')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeInTheDocument()
  })

  it('submits credentials via login', async () => {
    loginMock.mockResolvedValue({})
    renderWithProviders(<LoginPage />)

    fireEvent.change(screen.getByLabelText('Usuário'), {
      target: { value: 'admin' },
    })
    fireEvent.change(screen.getByLabelText('Senha'), {
      target: { value: 'admin123' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith('admin', 'admin123')
    })
  })

  it('shows an error when credentials are invalid', async () => {
    loginMock.mockRejectedValue(new Error('invalid'))
    renderWithProviders(<LoginPage />)

    fireEvent.change(screen.getByLabelText('Usuário'), {
      target: { value: 'admin' },
    })
    fireEvent.change(screen.getByLabelText('Senha'), {
      target: { value: 'wrong' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(
      await screen.findByText('Email ou senha inválidos'),
    ).toBeInTheDocument()
  })

  /**
   * A entrada do app termina aqui: o splash dissolve e o cartão sobe em
   * cascata. Sem estas classes a tela volta a aparecer de uma vez — o teste
   * existe para a animação não sumir num refactor de className.
   */
  it('entra em cascata (marca → título → formulário)', () => {
    const { container } = renderWithProviders(<LoginPage />)

    expect(container.querySelector('.gf-anim-rise-in')).toBeInTheDocument()
    expect(document.querySelectorAll('.gf-anim-rise-in').length).toBeGreaterThanOrEqual(3)
    expect(container.querySelector('.gf-anim-delay-1')).toBeInTheDocument()
    expect(document.querySelector('.gf-anim-delay-3')).toBeInTheDocument()
    // Fundo animado (ambiente) — aria-hidden, não entra na árvore acessível.
    expect(container.querySelector('.gf-anim-drift')).toBeInTheDocument()
  })
})
