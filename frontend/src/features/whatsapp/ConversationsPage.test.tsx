import { fireEvent, screen, waitFor } from '@testing-library/react'
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
import { ConversationsPage } from './ConversationsPage'

const conversations = [
  {
    id: 1,
    account_id: 'primary',
    customer_phone: '5511999999999',
    customer_codigo: 'CLT-001',
    state: 'IDLE',
    human_operator: null,
    message_count: 2,
    last_message: 'Quero um P13',
    created_at: '2026-08-01T10:00:00',
    updated_at: '2026-08-01T10:05:00',
  },
]

const detail = {
  ...conversations[0],
  draft: null,
  messages: [
    {
      id: 1,
      direction: 'INCOMING',
      sender: 'customer',
      content: 'Quero um P13',
      message_type: 'text',
      created_at: '2026-08-01T10:00:00',
    },
    {
      id: 2,
      direction: 'OUTGOING',
      sender: 'assistant',
      content: 'Ótimo! Qual endereço?',
      message_type: 'text',
      created_at: '2026-08-01T10:01:00',
    },
  ],
}

const render = () => renderWithProviders(<ConversationsPage />)

describe('ConversationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === '/whatsapp/conversations') return { data: { conversations } }
      if (url === '/whatsapp/conversations/1') return { data: detail }
      return { data: {} }
    })
  })

  it('shows the empty state when there are no conversations', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === '/whatsapp/conversations') return { data: { conversations: [] } }
      return { data: {} }
    })
    render()

    await waitFor(() => {
      expect(screen.getByText('Nenhuma conversa ativa')).toBeInTheDocument()
    })
    expect(screen.getByText('Selecione uma conversa')).toBeInTheDocument()
  })

  it('renders the conversation list with state labels', async () => {
    render()

    await waitFor(() => {
      expect(screen.getByText('Conversas Ativas')).toBeInTheDocument()
    })
    expect(screen.getByText('CLT-001')).toBeInTheDocument()
    expect(screen.getByText('Quero um P13')).toBeInTheDocument()
    expect(screen.getByText('Ociosa')).toBeInTheDocument()
  })

  it('loads and shows the conversation detail with messages', async () => {
    render()

    const item = await screen.findByText('CLT-001')
    fireEvent.click(item)

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith('/whatsapp/conversations/1')
    })
    // A mensagem aparece na prévia da lista e no detalhe → usar getAllByText
    expect(screen.getAllByText('Quero um P13').length).toBeGreaterThan(0)
    expect(screen.getByText('Ótimo! Qual endereço?')).toBeInTheDocument()
    expect(screen.getByText('customer')).toBeInTheDocument()
  })

  it('shows the draft summary in the detail panel', async () => {
    const withDraft = {
      ...detail,
      draft: {
        customer_name: 'Maria',
        items: [{ product_nome: 'P13', quantity: 2, subtotal: 130 }],
        total: 130,
      },
    }
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === '/whatsapp/conversations') return { data: { conversations } }
      if (url === '/whatsapp/conversations/1') return { data: withDraft }
      return { data: {} }
    })
    render()

    const item = await screen.findByText('CLT-001')
    fireEvent.click(item)

    expect(await screen.findByText('Draft do Pedido')).toBeInTheDocument()
    expect(screen.getByText(/P13 × 2 = R\$ 130/)).toBeInTheDocument()
  })

  it('takes over a conversation via the takeover button', async () => {
    render()

    const item = await screen.findByText('CLT-001')
    fireEvent.click(item)

    const takeover = await screen.findByRole('button', { name: /Assumir/i })
    fireEvent.click(takeover)

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        '/whatsapp/conversations/1/takeover',
        { operator: 'Operador' },
      )
    })
  })
})
