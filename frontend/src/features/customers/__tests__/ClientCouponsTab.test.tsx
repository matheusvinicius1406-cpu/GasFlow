import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

const mockGet = vi.fn()
vi.mock('@/lib/api/client', () => ({
  apiClient: { get: (...args: unknown[]) => mockGet(...args) },
}))

import { ClientCouponsTab } from '../ClientCouponsTab'

const sampleCoupon = {
  id: 'c1',
  code: 'BEMVINDO-000001',
  type: 'FIXED',
  value: 10,
  end_date: '2026-12-31T00:00:00Z',
  is_referral: true,
  status: 'active',
}

describe('ClientCouponsTab', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('shows loading spinner', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    const { container } = renderWithProviders(<ClientCouponsTab clientCodigo="000001" />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders coupons list', async () => {
    mockGet.mockResolvedValue({ data: { items: [sampleCoupon] } })
    renderWithProviders(<ClientCouponsTab clientCodigo="000001" />)
    await waitFor(() => {
      expect(screen.getByText('BEMVINDO-000001')).toBeInTheDocument()
    })
    expect(screen.getByText('Indicação')).toBeInTheDocument()
  })

  it('shows empty state when no coupons', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    renderWithProviders(<ClientCouponsTab clientCodigo="000001" />)
    await waitFor(() => {
      expect(screen.getByText('Nenhum cupom')).toBeInTheDocument()
    })
  })

  it('shows empty state on API error', async () => {
    mockGet.mockRejectedValue(new Error('fail'))
    renderWithProviders(<ClientCouponsTab clientCodigo="000001" />)
    await waitFor(() => {
      expect(screen.getByText('Nenhum cupom')).toBeInTheDocument()
    })
  })

  it('displays coupon count in header', async () => {
    mockGet.mockResolvedValue({
      data: { items: [sampleCoupon, { ...sampleCoupon, id: 'c2', code: 'INDICA-XYZ' }] },
    })
    renderWithProviders(<ClientCouponsTab clientCodigo="000001" />)
    await waitFor(() => {
      expect(screen.getByText(/Cupons \(2\)/)).toBeInTheDocument()
    })
  })
})
