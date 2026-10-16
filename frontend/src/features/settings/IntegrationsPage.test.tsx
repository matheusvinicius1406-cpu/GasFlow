import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

const { authState } = vi.hoisted(() => ({
  authState: { canWrite: true },
}))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ hasPermission: () => authState.canWrite, isLoading: false }),
}))

vi.mock('@/lib/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

import { apiClient } from '@/lib/api/client'
import { IntegrationsPage } from './IntegrationsPage'

const integrations = [
  {
    id: 'int-1',
    name: 'Revenda Centro',
    description: null,
    base_url: 'https://revenda.com.br',
    orders_path: '/api/pedidos',
    auth_type: 'token',
    has_credentials: true,
    import_token: 'tok_abcdef123456',
    sync_interval_minutes: 5,
    is_active: true,
    last_sync_at: null,
    last_sync_status: null,
  },
]

describe('IntegrationsPage', () => {
  beforeEach(() => {
    authState.canWrite = true
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockResolvedValue({ data: { integrations } })
    vi.mocked(apiClient.post).mockResolvedValue({ data: {} })
    vi.mocked(apiClient.delete).mockResolvedValue({ data: {} })
  })

  it('renders the integrations list', async () => {
    renderWithProviders(<IntegrationsPage />)
    await waitFor(() => {
      expect(screen.getByText('Revenda Centro')).toBeInTheDocument()
    })
    expect(screen.getByText('Ativa')).toBeInTheDocument()
    expect(screen.getByText('https://revenda.com.br')).toBeInTheDocument()
  })

  it('shows the empty state when there are no integrations', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { integrations: [] } })
    renderWithProviders(<IntegrationsPage />)
    await waitFor(() => {
      expect(screen.getByText('Nenhuma integração')).toBeInTheDocument()
    })
  })

  it('hides the write actions without the integration.write permission', async () => {
    authState.canWrite = false
    renderWithProviders(<IntegrationsPage />)
    await waitFor(() => {
      expect(screen.getByText('Revenda Centro')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: /Nova integração/ })).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Rotacionar token de Revenda Centro' })
    ).not.toBeInTheDocument()
  })

  it('shows the error state when loading fails', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('boom'))
    renderWithProviders(<IntegrationsPage />)
    await waitFor(() => {
      expect(screen.getByText('Não foi possível carregar as integrações.')).toBeInTheDocument()
    })
  })
})
