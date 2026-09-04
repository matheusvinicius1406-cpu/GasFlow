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
import { AutomationsPage } from './AutomationsPage'

const emptyMetrics = { active_rules: 0, sent: 0, pending: 0, success_rate: 0 }
const filledMetrics = { active_rules: 1, sent: 3, pending: 1, success_rate: 75 }

const rule = {
  id: 1,
  name: 'Recompra P13',
  description: 'Cliente sem pedido há 30+ dias',
  trigger_type: 'REORDER_OPPORTUNITY',
  status: 'ACTIVE',
  cooldown_days: 7,
  requires_approval: true,
}

describe('AutomationsPage', () => {
  let rules: unknown[]
  let metrics: unknown
  let fail: boolean

  beforeEach(() => {
    vi.clearAllMocks()
    rules = []
    metrics = emptyMetrics
    fail = false
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (fail) throw new Error('boom')
      if (url.startsWith('/automation/whatsapp/rules')) {
        return { data: { rules } }
      }
      if (url.startsWith('/automation/whatsapp/executions')) {
        return { data: { executions: [] } }
      }
      return { data: metrics } // metrics
    })
    vi.mocked(apiClient.post).mockResolvedValue({ data: { success: true } })
  })

  it('renders metrics and the rules list', async () => {
    rules = [rule]
    metrics = filledMetrics
    renderWithProviders(<AutomationsPage />)

    await waitFor(() => {
      expect(screen.getByText('Recompra P13')).toBeInTheDocument()
    })
    expect(screen.getByText('Regras Ativas')).toBeInTheDocument()
    expect(screen.getByText('Enviados')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('shows the empty state when there are no rules', async () => {
    renderWithProviders(<AutomationsPage />)
    await waitFor(() => {
      expect(screen.getByText('Nenhuma regra de automação')).toBeInTheDocument()
    })
  })

  it('shows the error state when loading fails', async () => {
    fail = true
    renderWithProviders(<AutomationsPage />)

    await waitFor(() => {
      expect(screen.getByText('Erro ao carregar automações')).toBeInTheDocument()
    })
  })

  it('opens the create form and creates a rule', async () => {
    renderWithProviders(<AutomationsPage />)

    const newRule = await screen.findByRole('button', { name: /Nova Regra/i })
    newRule.click()

    const name = await screen.findByPlaceholderText('Ex: Recompra P13')
    fireEvent.change(name, { target: { value: 'Novos 30d' } })
    const template = screen.getByPlaceholderText(/Olá \{\{customer_name\}\}/)
    fireEvent.change(template, { target: { value: 'Olá! Quer pedir?' } })

    const create = screen.getByRole('button', { name: 'Criar Regra' })
    create.click()

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        '/automation/whatsapp/rules',
        expect.objectContaining({ name: 'Novos 30d' })
      )
    })
  })
})
