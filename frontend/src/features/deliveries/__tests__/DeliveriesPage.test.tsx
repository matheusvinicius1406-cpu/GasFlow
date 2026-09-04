import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

// DeliveriesPage uses several hooks; expose them all.
let deliveriesState: {
  data: { deliveries: unknown[]; count: number } | null
  isLoading: boolean
  error: Error | null
  refetch: ReturnType<typeof vi.fn>
} = { data: { deliveries: [], count: 0 }, isLoading: false, error: null, refetch: vi.fn() }
let driversState: { drivers: unknown[]; count: number } | null = { drivers: [], count: 0 }
let summaryState: unknown = { deliveries: { total: 0, by_status: {} }, drivers: { total: 0, available: 0 } }

vi.mock('@/lib/api/hooks', () => ({
  useDeliveries: () => deliveriesState,
  useDeliveryDrivers: () => ({ data: driversState }),
  useDeliverySummary: () => ({ data: summaryState }),
  useCreateDelivery: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAssignDelivery: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateDeliveryStatus: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

import { DeliveriesPage } from '../DeliveriesPage'

const sampleDelivery = {
  id: 'DLV-1',
  order_id: 'ORD-1',
  status: 'PENDING',
  customer_codigo: 'CLT-001',
  customer_name: 'João da Silva',
  created_at: '2026-09-01T10:00:00',
}

describe('DeliveriesPage', () => {
  beforeEach(() => {
    deliveriesState = { data: { deliveries: [], count: 0 }, isLoading: false, error: null, refetch: vi.fn() }
    driversState = { drivers: [], count: 0 }
    summaryState = { deliveries: { total: 0, by_status: {} }, drivers: { total: 0, available: 0 } }
  })

  it('shows loading spinner while loading', () => {
    deliveriesState = { ...deliveriesState, isLoading: true }
    const { container } = renderWithProviders(<DeliveriesPage />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders deliveries list', async () => {
    deliveriesState = { ...deliveriesState, data: { deliveries: [sampleDelivery], count: 1 } }
    renderWithProviders(<DeliveriesPage />)
    await waitFor(() => {
      expect(screen.getByText('João da Silva')).toBeInTheDocument()
    })
  })

  it('shows empty state when no deliveries', () => {
    renderWithProviders(<DeliveriesPage />)
    expect(screen.getByText(/Nenhuma entrega/i)).toBeInTheDocument()
  })

  it('shows error state on failure', () => {
    deliveriesState = { ...deliveriesState, error: new Error('boom') }
    renderWithProviders(<DeliveriesPage />)
    expect(screen.getByText('Não foi possível carregar as entregas.')).toBeInTheDocument()
  })
})