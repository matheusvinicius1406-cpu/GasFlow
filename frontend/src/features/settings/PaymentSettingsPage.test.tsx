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
import { PaymentSettingsPage } from './PaymentSettingsPage'

const methods = [
  {
    id: 'm1',
    code: 'PIX',
    name: 'PIX',
    payment_type: 'PIX',
    enabled: true,
    display_order: 1,
    requires_confirmation: false,
    description: '',
    fee_type: 'NONE',
    fee_value: 0,
    discount_type: 'NONE',
    discount_value: 0,
  },
  {
    id: 'm2',
    code: 'CASH',
    name: 'Dinheiro',
    payment_type: 'CASH',
    enabled: false,
    display_order: 2,
    requires_confirmation: false,
    description: '',
    fee_type: 'NONE',
    fee_value: 0,
    discount_type: 'NONE',
    discount_value: 0,
  },
]

const pixConfigs = [
  {
    id: 'p1',
    key: 'maria@email.com',
    key_type: 'EMAIL',
    holder_name: 'Maria Silva',
    holder_document: '12345678901',
    institution: 'Banco Teste',
    active: true,
  },
]

function mockGet(methodsData: unknown[], configsData: unknown[]) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/payments/methods') return { data: { methods: methodsData } }
    if (url === '/payments/pix') return { data: { configs: configsData } }
    return { data: {} }
  })
}

const render = () => renderWithProviders(<PaymentSettingsPage />)

describe('PaymentSettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet([], [])
  })

  it('shows the empty state for payment methods', async () => {
    render()

    await waitFor(() => {
      expect(screen.getByText('Métodos de Pagamento')).toBeInTheDocument()
    })
    expect(screen.getByText('Nenhum método configurado')).toBeInTheDocument()
  })

  it('renders payment methods with status and toggles', async () => {
    mockGet(methods, [])
    render()

    await waitFor(() => {
      expect(screen.getAllByText('Dinheiro').length).toBeGreaterThan(0)
    })
    // "PIX" aparece no nome, no tipo e no select → usar getAllByText
    expect(screen.getAllByText('PIX').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Ativo').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Inativo').length).toBeGreaterThan(0)
  })

  it('shows the error state and recovers on retry', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('boom'))
    render()

    await waitFor(() => {
      expect(screen.getByText('Erro ao carregar métodos de pagamento')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Tentar novamente/i }))
    await waitFor(() => {
      expect(screen.getByText('Nenhum método configurado')).toBeInTheDocument()
    })
  })

  it('creates a payment method via the form', async () => {
    render()

    fireEvent.click(await screen.findByRole('button', { name: /Novo/i }))
    fireEvent.change(screen.getByPlaceholderText('Código (ex: PIX)'), {
      target: { value: 'TRANSFER' },
    })
    fireEvent.change(screen.getByPlaceholderText('Nome (ex: PIX)'), {
      target: { value: 'Transferência' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Salvar/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        '/payments/methods',
        expect.objectContaining({ code: 'TRANSFER', name: 'Transferência' }),
      )
    })
  })

  it('switches to the PIX tab and renders the PIX key', async () => {
    mockGet([], pixConfigs)
    render()

    fireEvent.click(screen.getByRole('button', { name: /Configuração PIX/i }))

    await waitFor(() => {
      expect(screen.getByText('maria@email.com')).toBeInTheDocument()
    })
    expect(screen.getByText('Ativa')).toBeInTheDocument()
  })
})
