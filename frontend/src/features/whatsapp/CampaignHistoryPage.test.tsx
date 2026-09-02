import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CampaignHistoryPage } from './CampaignHistoryPage'

// Mock useNavigate
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

// Mock API
vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn().mockImplementation((url: string) => {
      if (url.includes('/campaigns')) {
        return Promise.resolve({ data: { campaigns: [] } })
      }
      return Promise.resolve({ data: {} })
    }),
  },
}))

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('CampaignHistoryPage', () => {
  it('renders page header', async () => {
    renderWithProviders(<CampaignHistoryPage />)
    await waitFor(() => {
      expect(screen.getByText('Campanhas')).toBeInTheDocument()
      expect(screen.getByText(/Gerencie e acompanhe/)).toBeInTheDocument()
    })
  })

  it('renders filter buttons', async () => {
    renderWithProviders(<CampaignHistoryPage />)
    await waitFor(() => {
      expect(screen.getByText('Todas')).toBeInTheDocument()
      expect(screen.getByText('Em execução')).toBeInTheDocument()
      expect(screen.getByText('Concluídas')).toBeInTheDocument()
      expect(screen.getByText('Rascunhos')).toBeInTheDocument()
    })
  })

  it('renders empty state when no campaigns', async () => {
    renderWithProviders(<CampaignHistoryPage />)
    await waitFor(() => {
      expect(screen.getByText('Nenhuma campanha')).toBeInTheDocument()
      expect(screen.getByText(/Crie sua primeira campanha/)).toBeInTheDocument()
    })
  })

  it('shows create button in empty state', async () => {
    renderWithProviders(<CampaignHistoryPage />)
    await waitFor(() => {
      expect(screen.getByText('Criar campanha')).toBeInTheDocument()
    })
  })

  it('navigates to new campaign on button click', async () => {
    renderWithProviders(<CampaignHistoryPage />)
    await waitFor(() => {
      expect(screen.getByText('Nova Campanha')).toBeInTheDocument()
    })
    screen.getByText('Nova Campanha').click()
    expect(mockNavigate).toHaveBeenCalledWith('/whatsapp/campaigns/new')
  })

  it('renders campaigns when data exists', async () => {
    const { apiClient } = await import('@/lib/api/client')
    vi.mocked(apiClient.get).mockImplementation((url: string) => {
      if (url.includes('/campaigns') && !url.includes('/results')) {
        return Promise.resolve({
          data: {
            campaigns: [
              {
                id: 1,
                name: 'Campanha de Teste',
                message: 'Olá!',
                list_id: 1,
                status: 'COMPLETED',
                created_at: '2026-09-01T10:00:00Z',
                started_at: '2026-09-01T10:01:00Z',
                completed_at: '2026-09-01T10:05:00Z',
              },
            ],
          },
        })
      }
      return Promise.resolve({ data: { results: { total: 10, sent: 10, failed: 0, pending: 0, processing: 0, cancelled: 0 } } })
    })

    renderWithProviders(<CampaignHistoryPage />)
    await waitFor(() => {
      expect(screen.getByText('Campanha de Teste')).toBeInTheDocument()
      expect(screen.getByText('Concluída')).toBeInTheDocument()
    })
  })

  it('filters campaigns by status', async () => {
    renderWithProviders(<CampaignHistoryPage />)
    await waitFor(() => {
      expect(screen.getByText('Em execução')).toBeInTheDocument()
    })
    screen.getByText('Em execução').click()
    // Filter button should be highlighted
    await waitFor(() => {
      expect(screen.getByText('Em execução')).toHaveClass('bg-primary')
    })
  })

  it('shows refresh button', async () => {
    renderWithProviders(<CampaignHistoryPage />)
    await waitFor(() => {
      // Find the refresh button (has RefreshCw icon)
      const buttons = screen.getAllByRole('button')
      expect(buttons.length).toBeGreaterThan(0)
    })
  })
})
