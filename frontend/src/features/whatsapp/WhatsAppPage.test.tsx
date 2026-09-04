import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { apiClient } from '@/lib/api/client'
import { WhatsAppPage } from './WhatsAppPage'

const connectedAccount = {
  id: 'primary',
  name: 'Principal',
  status: { state: 'connected', connected: true, hasQr: false },
  phone: '5511999999999',
  lastConnectedAt: null,
}

const disconnectedAccount = {
  id: 'secondary',
  name: 'Secundária',
  status: { state: 'disconnected', connected: false, hasQr: false },
  phone: null,
  lastConnectedAt: null,
}

describe('WhatsAppPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockResolvedValue({ data: { accounts: [] } })
    vi.mocked(apiClient.post).mockResolvedValue({ data: { success: true } })
  })

  it('shows the empty state when no accounts are configured', async () => {
    renderWithProviders(<WhatsAppPage />)
    await waitFor(() => {
      expect(screen.getByText('Nenhuma conta configurada')).toBeInTheDocument()
    })
  })

  it('renders accounts with status, phone and action buttons', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { accounts: [connectedAccount, disconnectedAccount] },
    })
    renderWithProviders(<WhatsAppPage />)

    await waitFor(() => {
      expect(screen.getByText('Principal')).toBeInTheDocument()
    })
    expect(screen.getByText('Secundária')).toBeInTheDocument()
    // Status labels appear both on the badge and the status row.
    expect(screen.getAllByText('Conectado').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Desconectado').length).toBeGreaterThan(0)
    expect(screen.getByText('5511999999999')).toBeInTheDocument()
    // Stats: Total 2, Conectadas 1
    expect(screen.getAllByText('Total').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Conectadas').length).toBeGreaterThan(0)
  })

  it('shows the service-unavailable card when the fetch fails', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('network'))
    renderWithProviders(<WhatsAppPage />)

    await waitFor(() => {
      expect(screen.getByText('Serviço Indisponível')).toBeInTheDocument()
    })
  })

  it('starts a disconnected account and refreshes the list', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { accounts: [disconnectedAccount] },
    })
    renderWithProviders(<WhatsAppPage />)

    const connect = await screen.findByRole('button', { name: /Conectar/i })
    connect.click()

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/accounts/secondary/start')
    })
    // onRefresh() fetches the accounts again after starting.
    expect(apiClient.get).toHaveBeenCalledTimes(2)
  })
})
