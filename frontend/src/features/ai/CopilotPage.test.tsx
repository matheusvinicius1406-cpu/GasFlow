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
import { CopilotPage } from './CopilotPage'

describe('CopilotPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // jsdom não implementa scrollIntoView — o componente o usa no useEffect.
    Element.prototype.scrollIntoView = vi.fn()
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        message: 'Temos 50 unidades de P13 em estoque.',
        intent: 'inventory_lookup',
        tool_used: 'inventory',
        requires_confirmation: false,
        error: null,
        conversation_id: 'conv-123',
      },
    })
  })

  it('shows the welcome message with examples on first load', () => {
    renderWithProviders(<CopilotPage />)
    expect(screen.getByText('Olá! Sou o assistente do GasFlow.')).toBeInTheDocument()
    expect(screen.getByText(/Quanto temos de P13\?/)).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Digite sua pergunta...')).toBeInTheDocument()
  })

  it('sends a message and renders the assistant reply', async () => {
    renderWithProviders(<CopilotPage />)

    const input = screen.getByPlaceholderText('Digite sua pergunta...')
    fireEvent.change(input, { target: { value: 'Quanto temos de P13?' } })

    const sendButton = screen.getByRole('button')
    fireEvent.click(sendButton)

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/ai/chat', {
        message: 'Quanto temos de P13?',
        conversation_id: null,
      })
    })
    expect(
      await screen.findByText('Temos 50 unidades de P13 em estoque.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Tool: inventory')).toBeInTheDocument()
    expect(screen.getByText('Quanto temos de P13?')).toBeInTheDocument()
  })

  it('sends via Enter key', async () => {
    renderWithProviders(<CopilotPage />)

    const input = screen.getByPlaceholderText('Digite sua pergunta...')
    fireEvent.change(input, { target: { value: 'Qual o estoque?' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalled()
    })
  })

  it('shows an error bubble when the chat request fails', async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(new Error('network'))
    renderWithProviders(<CopilotPage />)

    const input = screen.getByPlaceholderText('Digite sua pergunta...')
    fireEvent.change(input, { target: { value: 'Quanto temos de P13?' } })
    fireEvent.click(screen.getByRole('button'))

    expect(
      await screen.findByText('Desculpe, ocorreu um erro ao processar sua mensagem.'),
    ).toBeInTheDocument()
  })
})