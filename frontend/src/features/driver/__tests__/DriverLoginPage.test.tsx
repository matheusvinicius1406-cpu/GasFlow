import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

import { DriverLoginPage } from '../DriverLoginPage'

function jsonResponse(body: unknown, ok = true) {
  return { ok, json: async () => body } as Response
}

describe('DriverLoginPage', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.stubGlobal('fetch', vi.fn())
  })

  it('keeps the submit button disabled until both fields are filled', () => {
    renderWithProviders(<DriverLoginPage />)
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('Nome ou telefone'), { target: { value: 'joao' } })
    fireEvent.change(screen.getByPlaceholderText('Senha'), { target: { value: 'segredo' } })
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeEnabled()
  })

  it('stores the token on a successful login', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ success: true, token: 'tok', driver_id: 'd1', tenant_id: 't1' })
    )
    renderWithProviders(<DriverLoginPage />)

    fireEvent.change(screen.getByPlaceholderText('Nome ou telefone'), { target: { value: 'joao' } })
    fireEvent.change(screen.getByPlaceholderText('Senha'), { target: { value: 'segredo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => {
      expect(window.localStorage.getItem('driver_token')).toBe('tok')
    })
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/driver/auth/login',
      expect.objectContaining({ method: 'POST' })
    )
    expect(window.localStorage.getItem('driver_id')).toBe('d1')
  })

  it('shows the backend error message on invalid credentials', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ success: false, error: 'Credenciais inválidas' }, false)
    )
    renderWithProviders(<DriverLoginPage />)

    fireEvent.change(screen.getByPlaceholderText('Nome ou telefone'), { target: { value: 'joao' } })
    fireEvent.change(screen.getByPlaceholderText('Senha'), { target: { value: 'errada' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => {
      expect(screen.getByText('Credenciais inválidas')).toBeInTheDocument()
    })
    expect(window.localStorage.getItem('driver_token')).toBeNull()
  })
})
