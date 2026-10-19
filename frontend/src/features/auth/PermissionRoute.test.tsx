import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { renderWithProviders } from '@/test/utils'
import { ACCESS_TOKEN_KEY } from '@/lib/api/session'

const { meMock } = vi.hoisted(() => ({ meMock: vi.fn() }))

vi.mock('@/lib/api/client', () => ({
  api: {
    auth: {
      me: meMock,
      logout: vi.fn(),
    },
  },
}))

import { AuthProvider, PermissionRoute } from './AuthProvider'

function renderGuard(permissions: string[]) {
  return renderWithProviders(
    <AuthProvider>
      <Routes>
        <Route
          path="/finance"
          element={
            <PermissionRoute permissions={permissions}>
              <div>página-protegida</div>
            </PermissionRoute>
          }
        />
        <Route path="/" element={<div>dashboard</div>} />
      </Routes>
    </AuthProvider>,
    { route: '/finance' }
  )
}

describe('PermissionRoute', () => {
  beforeEach(() => {
    localStorage.clear()
    meMock.mockReset()
  })

  it('sem a permissão mostra o estado unificado em vez de redirecionar', async () => {
    renderGuard(['finance.read'])

    expect(await screen.findByRole('heading', { name: 'Sem permissão' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ir para o início' })).toBeInTheDocument()
    expect(screen.queryByText('página-protegida')).not.toBeInTheDocument()
    // O bug antigo: quedava no dashboard sem avisar nada.
    expect(screen.queryByText('dashboard')).not.toBeInTheDocument()
  })

  it('com a permissão renderiza o conteúdo protegido', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'token-de-teste')
    meMock.mockResolvedValue({
      data: { id: 'u1', username: 'oper', permissions: ['finance.read'] },
    })

    renderGuard(['finance.read'])

    expect(await screen.findByText('página-protegida')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sem permissão' })).not.toBeInTheDocument()
  })

  it('permissão de módulo (finance.*) cobre finance.read', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'token-de-teste')
    meMock.mockResolvedValue({
      data: { id: 'u1', username: 'oper', permissions: ['finance.*'] },
    })

    renderGuard(['finance.read'])

    expect(await screen.findByText('página-protegida')).toBeInTheDocument()
  })

  it('sem sessão e sem permissão nenhuma, mostra o estado negado (não manda pro login)', async () => {
    renderGuard(['audit.view'])

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Sem permissão' })).toBeInTheDocument()
    })
    expect(meMock).not.toHaveBeenCalled()
  })
})
