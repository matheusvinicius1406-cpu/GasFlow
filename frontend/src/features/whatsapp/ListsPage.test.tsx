import { screen, waitFor, fireEvent } from '@testing-library/react'
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
import { ListsPage } from './ListsPage'

const lists = [
  { id: 1, name: 'Clientes Ativos', description: null, contactCount: 12, customerCount: 8 },
  { id: 2, name: 'Prospectos', description: null, contactCount: 3, customerCount: 0 },
]

const listContacts = {
  total: 1,
  contacts: [{ id: 42, phone: '5511999999999', name: 'Maria', push_name: null, business_name: null }],
}

const listCustomers = {
  total: 1,
  customers: [{ id: 7, contact_id: 42, customer_status: 'CUSTOMER', contact: { phone: '5511999999999' } }],
}

describe('ListsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === '/whatsapp/lists') return { data: { total: lists.length, lists } }
      if (url === '/whatsapp/lists/1/contacts') return { data: listContacts }
      if (url === '/whatsapp/lists/1/customers') return { data: listCustomers }
      return { data: { total: 0 } }
    })
    vi.mocked(apiClient.post).mockResolvedValue({ data: { ok: true } })
    vi.mocked(apiClient.delete).mockResolvedValue({ data: { ok: true } })
  })

  it('renders the lists with contact and customer counts', async () => {
    renderWithProviders(<ListsPage />)

    await waitFor(() => {
      expect(screen.getByText('Clientes Ativos')).toBeInTheDocument()
    })
    expect(screen.getByText('Prospectos')).toBeInTheDocument()
  })

  it('loads members when a list is selected', async () => {
    renderWithProviders(<ListsPage />)

    const row = await screen.findByRole('button', { name: 'Clientes Ativos' })
    fireEvent.click(row)

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith('/whatsapp/lists/1/contacts')
    })
    expect(apiClient.get).toHaveBeenCalledWith('/whatsapp/lists/1/customers')
    expect(await screen.findByText('Maria')).toBeInTheDocument()
  })

  it('seeds the default lists', async () => {
    renderWithProviders(<ListsPage />)

    fireEvent.click(await screen.findByRole('button', { name: /Semear listas/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/lists/seed')
    })
  })

  it('syncs the selected list with the CRM', async () => {
    renderWithProviders(<ListsPage />)

    fireEvent.click(await screen.findByRole('button', { name: 'Clientes Ativos' }))
    const sync = await screen.findByRole('button', { name: /Sincronizar/i })
    fireEvent.click(sync)

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/lists/1/sync')
    })
  })

  it('shows the error state when the fetch fails', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('boom'))
    renderWithProviders(<ListsPage />)

    await waitFor(() => {
      expect(screen.getByText('Não foi possível carregar as listas.')).toBeInTheDocument()
    })
  })
})
