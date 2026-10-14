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
import { WhatsAppCustomersPage } from './WhatsAppCustomersPage'

const optedIn = {
  id: 1,
  contact_id: 42,
  customer_status: 'CUSTOMER',
  marketing_status: 'OPTED_IN',
  contact: { phone: '5511999999999', name: 'Maria', push_name: null, business_name: null },
}

const optedOut = {
  id: 2,
  contact_id: 43,
  customer_status: 'PROSPECT',
  marketing_status: 'OPTED_OUT',
  contact: { phone: '5511888888888', name: 'João', push_name: null, business_name: null },
}

const nodeContacts = [
  { id: 42, phone: '5511999999999', name: 'Maria', push_name: null, business_name: null },
  { id: 43, phone: '5511888888888', name: 'João', push_name: null, business_name: null },
]

describe('WhatsAppCustomersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === '/whatsapp/customers') {
        return { data: { total: 2, customers: [optedIn, optedOut] } }
      }
      if (url === '/whatsapp/node-contacts') {
        return { data: { total: nodeContacts.length, contacts: nodeContacts } }
      }
      return { data: {} }
    })
    vi.mocked(apiClient.post).mockResolvedValue({ data: { ok: true } })
    vi.mocked(apiClient.put).mockResolvedValue({ data: { ok: true } })
  })

  it('renders the marketing base with the real consent status', async () => {
    renderWithProviders(<WhatsAppCustomersPage />)

    await waitFor(() => {
      expect(screen.getByText('Maria')).toBeInTheDocument()
    })
    expect(screen.getByText('João')).toBeInTheDocument()
    expect(screen.getAllByText('OPTED_IN').length).toBeGreaterThan(0)
    expect(screen.getAllByText('OPTED_OUT').length).toBeGreaterThan(0)
  })

  it('disables the opt-out action for a contact already opted out', async () => {
    renderWithProviders(<WhatsAppCustomersPage />)

    const optOut = await screen.findByRole('button', { name: 'Registrar opt-out do cliente 2' })
    expect(optOut).toBeDisabled()
    // O opt-in continua liberado para quem saiu.
    expect(screen.getByRole('button', { name: 'Registrar opt-in do cliente 2' })).toBeEnabled()
  })

  it('changes the customer status through the proxy', async () => {
    renderWithProviders(<WhatsAppCustomersPage />)

    const select = await screen.findByLabelText('Status do cliente 1')
    fireEvent.change(select, { target: { value: 'PROSPECT' } })

    await waitFor(() => {
      expect(apiClient.put).toHaveBeenCalledWith('/whatsapp/customers/1/status', {
        status: 'PROSPECT',
      })
    })
  })

  it('promotes the selected Node contact (not a raw typed id)', async () => {
    renderWithProviders(<WhatsAppCustomersPage />)

    const picker = await screen.findByLabelText('Contato a promover a cliente')
    fireEvent.change(picker, { target: { value: '43' } })
    fireEvent.click(screen.getByRole('button', { name: /Promover/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/customers/43/promote', {
        status: 'UNKNOWN',
      })
    })
  })

  it('triggers the CRM sync', async () => {
    renderWithProviders(<WhatsAppCustomersPage />)

    fireEvent.click(await screen.findByRole('button', { name: /Sincronizar/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/customers/sync')
    })
  })

  it('shows the error state when the fetch fails', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('boom'))
    renderWithProviders(<WhatsAppCustomersPage />)

    await waitFor(() => {
      expect(screen.getByText('Não foi possível carregar os clientes.')).toBeInTheDocument()
    })
  })
})
