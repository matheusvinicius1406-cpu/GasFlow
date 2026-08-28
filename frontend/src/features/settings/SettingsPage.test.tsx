import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { SettingsPage } from './SettingsPage'

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({
      data: {
        id: 'admin-001',
        username: 'admin',
        email: 'admin@gasflow.local',
        display_name: 'Administrator',
        status: 'ACTIVE',
        tenant_id: 'default',
        role: 'ADMIN',
        permissions: ['admin.*'],
      },
    }),
  },
}))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    logout: vi.fn(),
  }),
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

describe('SettingsPage', () => {
  it('renders profile after loading', async () => {
    renderWithProviders(<SettingsPage />)
    await waitFor(() => {
      expect(screen.getByText('Perfil do Usuário')).toBeInTheDocument()
    })
  })

  it('renders without crashing', async () => {
    const { container } = renderWithProviders(<SettingsPage />)
    await waitFor(() => {
      expect(container.firstChild).toBeTruthy()
    })
  })
})
