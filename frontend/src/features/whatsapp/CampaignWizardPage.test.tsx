import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CampaignWizardPage } from './CampaignWizardPage'

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
    get: vi.fn().mockResolvedValue({ data: { lists: [] } }),
    post: vi.fn().mockResolvedValue({ data: { id: 1, status: 'DRAFT' } }),
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

describe('CampaignWizardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders wizard header and step 1', async () => {
    renderWithProviders(<CampaignWizardPage />)
    await waitFor(() => {
      expect(screen.getByText('Nova Campanha')).toBeInTheDocument()
      expect(screen.getByText('Detalhes da Campanha')).toBeInTheDocument()
      expect(screen.getByText(/Nome da Campanha/)).toBeInTheDocument()
    })
  })

  it('shows step indicator with all steps', async () => {
    renderWithProviders(<CampaignWizardPage />)
    await waitFor(() => {
      expect(screen.getByText('Detalhes')).toBeInTheDocument()
      expect(screen.getByText('Mensagem')).toBeInTheDocument()
      expect(screen.getByText('Público')).toBeInTheDocument()
      expect(screen.getByText('Revisão')).toBeInTheDocument()
      expect(screen.getByText('Resultados')).toBeInTheDocument()
    })
  })

  it('validates name required on next', async () => {
    renderWithProviders(<CampaignWizardPage />)
    await waitFor(() => {
      expect(screen.getByText('Próximo')).toBeInTheDocument()
    })

    // Click next without filling name
    screen.getByText('Próximo').click()
    await waitFor(() => {
      expect(screen.getByText('Nome é obrigatório.')).toBeInTheDocument()
    })
  })

  it('navigates to step 2 with valid name', async () => {
    renderWithProviders(<CampaignWizardPage />)
    await waitFor(() => {
      expect(screen.getByText('Próximo')).toBeInTheDocument()
    })

    // Fill name
    const input = screen.getByPlaceholderText(/Promoção/)
    input.dispatchEvent(new Event('input', { bubbles: true }))
    // Simulate React controlled input
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value'
    )?.set
    if (nativeInputValueSetter) {
      nativeInputValueSetter.call(input, 'Campanha Teste')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    }

    screen.getByText('Próximo').click()
    await waitFor(() => {
      expect(screen.getByText('Mensagem da Campanha')).toBeInTheDocument()
    })
  })

  it('validates message required on step 2', async () => {
    renderWithProviders(<CampaignWizardPage />)
    await waitFor(() => {
      expect(screen.getByText('Próximo')).toBeInTheDocument()
    })

    // Go to step 2 (fill name first)
    const nameInput = screen.getByPlaceholderText(/Promoção/)
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value'
    )?.set
    if (setter) {
      setter.call(nameInput, 'Teste')
      nameInput.dispatchEvent(new Event('input', { bubbles: true }))
    }
    screen.getByText('Próximo').click()

    await waitFor(() => {
      expect(screen.getByText('Mensagem da Campanha')).toBeInTheDocument()
    })

    // Click next without message
    screen.getByText('Próximo').click()
    await waitFor(() => {
      expect(screen.getByText('Mensagem é obrigatória.')).toBeInTheDocument()
    })
  })

  it('shows back button on step 2', async () => {
    renderWithProviders(<CampaignWizardPage />)
    await waitFor(() => {
      expect(screen.getByText('Próximo')).toBeInTheDocument()
    })

    // Go to step 2
    const nameInput = screen.getByPlaceholderText(/Promoção/)
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value'
    )?.set
    if (setter) {
      setter.call(nameInput, 'Teste')
      nameInput.dispatchEvent(new Event('input', { bubbles: true }))
    }
    screen.getByText('Próximo').click()

    await waitFor(() => {
      expect(screen.getByText('Voltar')).toBeInTheDocument()
    })
  })

  it('navigates back to step 1 from step 2', async () => {
    renderWithProviders(<CampaignWizardPage />)
    await waitFor(() => {
      expect(screen.getByText('Próximo')).toBeInTheDocument()
    })

    // Go to step 2
    const nameInput = screen.getByPlaceholderText(/Promoção/)
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value'
    )?.set
    if (setter) {
      setter.call(nameInput, 'Teste')
      nameInput.dispatchEvent(new Event('input', { bubbles: true }))
    }
    screen.getByText('Próximo').click()

    await waitFor(() => {
      expect(screen.getByText('Voltar')).toBeInTheDocument()
    })

    screen.getByText('Voltar').click()
    await waitFor(() => {
      expect(screen.getByText('Detalhes da Campanha')).toBeInTheDocument()
    })
  })

  it('shows empty state when no lists available', async () => {
    renderWithProviders(<CampaignWizardPage />)
    await waitFor(() => {
      expect(screen.getByText('Próximo')).toBeInTheDocument()
    })

    // Go to step 2
    const nameInput = screen.getByPlaceholderText(/Promoção/)
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value'
    )?.set
    if (setter) {
      setter.call(nameInput, 'Teste')
      nameInput.dispatchEvent(new Event('input', { bubbles: true }))
    }
    screen.getByText('Próximo').click()

    await waitFor(() => {
      expect(screen.getByText('Mensagem da Campanha')).toBeInTheDocument()
    })

    // Fill message and go to step 3
    const textarea = screen.getByPlaceholderText(/Digite a mensagem/)
    const textareaSetter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      'value'
    )?.set
    if (textareaSetter) {
      textareaSetter.call(textarea, 'Mensagem de teste')
      textarea.dispatchEvent(new Event('input', { bubbles: true }))
    }
    screen.getByText('Próximo').click()

    await waitFor(() => {
      expect(screen.getByText('Nenhuma lista disponível')).toBeInTheDocument()
    })
  })

  it('shows WhatsApp message preview in template step', async () => {
    renderWithProviders(<CampaignWizardPage />)
    await waitFor(() => {
      expect(screen.getByText('Próximo')).toBeInTheDocument()
    })

    // Go to step 2
    const nameInput = screen.getByPlaceholderText(/Promoção/)
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value'
    )?.set
    if (setter) {
      setter.call(nameInput, 'Teste')
      nameInput.dispatchEvent(new Event('input', { bubbles: true }))
    }
    screen.getByText('Próximo').click()

    await waitFor(() => {
      expect(screen.getByText('Pré-visualização')).toBeInTheDocument()
    })
  })

  it('displays character count in template step', async () => {
    renderWithProviders(<CampaignWizardPage />)
    await waitFor(() => {
      expect(screen.getByText('Próximo')).toBeInTheDocument()
    })

    // Go to step 2
    const nameInput = screen.getByPlaceholderText(/Promoção/)
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value'
    )?.set
    if (setter) {
      setter.call(nameInput, 'Teste')
      nameInput.dispatchEvent(new Event('input', { bubbles: true }))
    }
    screen.getByText('Próximo').click()

    await waitFor(() => {
      expect(screen.getByText(/\/4096 caracteres/)).toBeInTheDocument()
    })
  })
})
