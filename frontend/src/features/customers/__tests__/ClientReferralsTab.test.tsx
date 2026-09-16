import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

const mockGet = vi.fn()
vi.mock('@/lib/api/client', () => ({
  apiClient: { get: (...args: unknown[]) => mockGet(...args) },
}))

import { ClientReferralsTab } from '../ClientReferralsTab'

const sampleReferral = {
  id: 'r1',
  invite_token: 'GF-INV-abc123',
  referred_name: 'Maria',
  referred_client_codigo: '000002',
  created_at: '2026-09-01T00:00:00Z',
  completed: true,
}

describe('ClientReferralsTab', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('shows loading spinner', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    const { container } = renderWithProviders(<ClientReferralsTab clientCodigo="000001" />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders referrals list with meta', async () => {
    mockGet.mockResolvedValue({
      data: {
        items: [sampleReferral],
        total: 1,
        completed: 1,
        pending: 0,
        monthly_limit: 10,
      },
    })
    renderWithProviders(<ClientReferralsTab clientCodigo="000001" />)
    await waitFor(() => {
      expect(screen.getByText('Maria')).toBeInTheDocument()
    })
    expect(screen.getByText('Concluída')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument() // monthly_limit
  })

  it('shows empty state when no referrals', async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, completed: 0, pending: 0, monthly_limit: 10 },
    })
    renderWithProviders(<ClientReferralsTab clientCodigo="000001" />)
    await waitFor(() => {
      expect(screen.getByText('Nenhuma indicação')).toBeInTheDocument()
    })
  })

  it('shows empty state on API error', async () => {
    mockGet.mockRejectedValue(new Error('fail'))
    renderWithProviders(<ClientReferralsTab clientCodigo="000001" />)
    await waitFor(() => {
      expect(screen.getByText('Nenhuma indicação')).toBeInTheDocument()
    })
  })

  it('displays pending referral correctly', async () => {
    mockGet.mockResolvedValue({
      data: {
        items: [{ ...sampleReferral, referred_name: null, completed: false }],
        total: 1,
        completed: 0,
        pending: 1,
        monthly_limit: 10,
      },
    })
    renderWithProviders(<ClientReferralsTab clientCodigo="000001" />)
    await waitFor(() => {
      expect(screen.getByText('Pendente')).toBeInTheDocument()
    })
    expect(screen.getByText('—')).toBeInTheDocument() // no referred_name
  })
})
