import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

vi.mock('@/lib/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}))

import { apiClient } from '@/lib/api/client'
import { WorkflowsPage } from '../WorkflowsPage'

const runs = [
  { id: 'abcdef123456', workflow_id: 'wf-1', status: 'RUNNING', started_at: '2026-09-01T10:00:00' },
]
const approvals = [
  { id: 'a1', action: 'Excluir cliente', status: 'PENDING', risk_level: 'HIGH', created_at: '2026-09-01T10:00:00' },
]
const workflows = [{ id: 'wf-1', name: 'Boas-vindas', status: 'ACTIVE', steps: 3 }]

describe('WorkflowsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === '/automation/workflows') return { data: { workflows } }
      if (url === '/automation/runs') return { data: { runs } }
      if (url === '/automation/approvals') return { data: { approvals } }
      if (url === '/automation/kill-switch') return { data: { active: false } }
      return { data: {} }
    })
    vi.mocked(apiClient.post).mockResolvedValue({ data: { active: true } })
  })

  it('renders the runs list once loaded', async () => {
    renderWithProviders(<WorkflowsPage />)
    await waitFor(() => {
      expect(screen.getByText('abcdef12')).toBeInTheDocument()
    })
    expect(screen.getByText('wf-1')).toBeInTheDocument()
  })

  it('lists pending approvals on the approvals tab', async () => {
    renderWithProviders(<WorkflowsPage />)
    const tab = await screen.findByRole('button', { name: /Aprovações/ })
    fireEvent.click(tab)
    await waitFor(() => {
      expect(screen.getByText('Excluir cliente')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Aprovar Excluir cliente' })).toBeInTheDocument()
  })

  it('arms the kill switch after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<WorkflowsPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Ligar kill switch' }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/automation/kill-switch', { active: true })
    })
  })

  it('shows the error state when loading fails', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('boom'))
    renderWithProviders(<WorkflowsPage />)
    await waitFor(() => {
      expect(screen.getByText('Não foi possível carregar as automações.')).toBeInTheDocument()
    })
  })
})
