import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

vi.mock('@/lib/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}))

import { apiClient } from '@/lib/api/client'
import { ContactsCrmPage } from './ContactsCrmPage'

const contacts = {
  total: 1,
  contacts: [
    {
      codigo: 'CLT-1',
      nome: 'Maria Souza',
      telefone: '5511999999999',
      has_name: true,
      is_whatsapp: true,
      marketing_status: 'OPT_IN',
      endereco_definido: true,
      last_sync_at: null,
    },
  ],
}

describe('ContactsCrmPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockResolvedValue({ data: contacts })
    vi.mocked(apiClient.post).mockResolvedValue({ data: { dedupe: { lidRemoved: 0, nameRemoved: 0 } } })
  })

  it('renders the contacts table', async () => {
    renderWithProviders(<ContactsCrmPage />)
    await waitFor(() => {
      expect(screen.getByText('Maria Souza')).toBeInTheDocument()
    })
    expect(screen.getByText('CLT-1')).toBeInTheDocument()
    expect(screen.getByText('Contatos (1)')).toBeInTheDocument()
  })

  it('shows the empty state when there are no contacts', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { total: 0, contacts: [] } })
    renderWithProviders(<ContactsCrmPage />)
    await waitFor(() => {
      expect(screen.getByText('Nenhum contato')).toBeInTheDocument()
    })
  })

  it('runs dedupe against the whatsapp service', async () => {
    renderWithProviders(<ContactsCrmPage />)
    const btn = await screen.findByRole('button', { name: /Deduplicar/ })
    fireEvent.click(btn)
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/contacts/dedupe')
    })
  })

  it('shows the error state when loading fails', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('boom'))
    renderWithProviders(<ContactsCrmPage />)
    await waitFor(() => {
      expect(screen.getByText('Não foi possível carregar os contatos.')).toBeInTheDocument()
    })
  })
})
