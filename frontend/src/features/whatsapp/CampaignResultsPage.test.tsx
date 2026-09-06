import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithRoute } from '@/test/utils'

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
import { CampaignResultsPage } from './CampaignResultsPage'

const campaign = {
  id: 1,
  name: 'Campanha P13',
  message: 'Olá! Temos P13 em promoção.',
  list_id: 2,
  status: 'COMPLETED',
  protection: 'OPT_IN',
  created_at: '2026-08-01T10:00:00',
  started_at: '2026-08-02T10:00:00',
  completed_at: '2026-08-02T11:00:00',
}

const results = {
  total: 10,
  pending: 1,
  processing: 0,
  sent: 8,
  failed: 1,
  cancelled: 0,
}

const recipients = [
  {
    campaign_id: 1,
    customer_id: 100,
    status: 'SENT',
    attempts: 1,
    created_at: '2026-08-02T10:00:00',
    started_at: null,
    completed_at: null,
    sent_at: '2026-08-02T10:00:05',
    last_error: null,
    error: null,
    provider_message_id: 'abc',
  },
  {
    campaign_id: 1,
    customer_id: 101,
    status: 'FAILED',
    attempts: 2,
    created_at: '2026-08-02T10:00:00',
    started_at: null,
    completed_at: null,
    sent_at: null,
    last_error: 'Invalid number',
    error: 'Invalid number',
    provider_message_id: null,
  },
]

function mockSuccess() {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url.endsWith('/campaigns/1')) return { data: campaign }
    if (url.endsWith('/campaigns/1/results')) return { data: { results } }
    if (url.endsWith('/campaigns/1/recipients')) return { data: { recipients } }
    return { data: {} }
  })
}

const render = () =>
  renderWithRoute(<CampaignResultsPage />, '/whatsapp/campaigns/:id', '/whatsapp/campaigns/1')

describe('CampaignResultsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSuccess()
  })

  it('shows the loading spinner while fetching', () => {
    vi.mocked(apiClient.get).mockImplementation(
      () => new Promise(() => {}) as never,
    )
    const { container } = render()
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders campaign header, progress and stats', async () => {
    render()

    await waitFor(() => {
      expect(screen.getByText('Campanha P13')).toBeInTheDocument()
    })
    expect(screen.getByText('Concluída')).toBeInTheDocument()
    expect(screen.getByText('Campanha #1')).toBeInTheDocument()
    // Progress: (8 sent + 1 failed) / 10 = 90%
    expect(screen.getByText('90%')).toBeInTheDocument()
    // Stats cards
    expect(screen.getByText('Enviados')).toBeInTheDocument()
    expect(screen.getByText('Taxa de sucesso')).toBeInTheDocument()
    expect(screen.getByText('Pendentes')).toBeInTheDocument()
    expect(screen.getByText('Falhas')).toBeInTheDocument()
    expect(screen.getByText('Total')).toBeInTheDocument()
    // Message preview
    expect(screen.getByText('Mensagem Enviada')).toBeInTheDocument()
    expect(screen.getByText('Olá! Temos P13 em promoção.')).toBeInTheDocument()
  })

  it('renders the recipients table with statuses', async () => {
    render()

    await waitFor(() => {
      expect(screen.getByText('Destinatários (2)')).toBeInTheDocument()
    })
    expect(screen.getByText('#100')).toBeInTheDocument()
    expect(screen.getByText('#101')).toBeInTheDocument()
    expect(screen.getAllByText('Enviado').length).toBeGreaterThan(0)
    expect(screen.getByText('Invalid number')).toBeInTheDocument()
  })

  it('shows the not-found card when the campaign is missing', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('404'))
    render()

    await waitFor(() => {
      expect(screen.getByText('Campanha não encontrada.')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Voltar' })).toBeInTheDocument()
  })

  it('pauses a RUNNING campaign', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.endsWith('/campaigns/1')) return { data: { ...campaign, status: 'RUNNING' } }
      if (url.endsWith('/campaigns/1/results')) return { data: { results } }
      if (url.endsWith('/campaigns/1/recipients')) return { data: { recipients } }
      return { data: {} }
    })
    render()

    const pause = await screen.findByRole('button', { name: /Pausar/i })
    fireEvent.click(pause)

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/campaigns/1/pause')
    })
  })

  it('cancels a campaign after confirmation', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.endsWith('/campaigns/1')) return { data: { ...campaign, status: 'PAUSED' } }
      if (url.endsWith('/campaigns/1/results')) return { data: { results } }
      if (url.endsWith('/campaigns/1/recipients')) return { data: { recipients } }
      return { data: {} }
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render()

    const cancel = await screen.findByRole('button', { name: /Cancelar/i })
    fireEvent.click(cancel)

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/campaigns/1/cancel')
    })
    vi.restoreAllMocks()
  })
})
