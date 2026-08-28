import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { DriversPage } from './DriversPage'

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({ data: [] }),
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

describe('DriversPage', () => {
  it('shows empty state when no drivers', async () => {
    renderWithProviders(<DriversPage />)
    await waitFor(() => {
      expect(screen.getByText(/Nenhum motorista/i)).toBeInTheDocument()
    })
  })

  it('renders without crashing', async () => {
    const { container } = renderWithProviders(<DriversPage />)
    await waitFor(() => {
      expect(container.firstChild).toBeTruthy()
    })
  })
})
