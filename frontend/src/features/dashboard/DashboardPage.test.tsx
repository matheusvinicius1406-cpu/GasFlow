import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { DashboardPage } from './DashboardPage'

// Mock useAuth
vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    user: { name: 'Test User', role: 'ADMIN' },
    isAuthenticated: true,
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Mock useDashboard
vi.mock('@/lib/api/hooks', () => ({
  useDashboard: () => ({
    data: {
      summary: {
        total_orders: 10,
        pending_orders: 2,
        confirmed_orders: 3,
        delivering_orders: 1,
        delivered_orders: 4,
        today_orders: 3,
        total_revenue: 5000,
        today_revenue: 1200,
        avg_ticket: 500,
      },
      clients: { total: 50 },
      products: { total: 12 },
      drivers: { total: 5 },
      financial: {
        total_received: 4500,
        today_received: 1000,
        total_pending: 500,
        total_expenses: 800,
        today_expenses: 200,
        cash_balance: 3700,
        result: 3700,
      },
      inventory: {
        total_items: 8,
        low_stock_count: 1,
        out_of_stock_count: 0,
        low_stock_products: [{ product_codigo: 'P13', quantity: 5, minimum: 10 }],
      },
      recent_orders: [
        { codigo: '10482', client_codigo: 'C001', total: 210, status: 'DELIVERING', payment_status: 'PAID', created_at: '2026-08-31T10:00:00' },
        { codigo: '10481', client_codigo: 'C002', total: 840, status: 'PENDING', payment_status: 'PENDING', created_at: '2026-08-31T09:30:00' },
      ],
      alerts: [
        { type: 'warning', title: '2 pedidos pendentes', description: 'Pedidos aguardando processamento', action: '/orders' },
        { type: 'warning', title: '1 produto com estoque baixo', description: 'Considere repor o estoque', action: '/inventory' },
      ],
      generated_at: '2026-08-31T12:00:00',
    },
    isLoading: false,
    error: null,
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

describe('DashboardPage', () => {
  it('renders greeting and KPIs', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText(/Bom dia|Boa tarde|Boa noite/)).toBeInTheDocument()
      expect(screen.getByText('Pedidos Hoje')).toBeInTheDocument()
      expect(screen.getByText('Faturamento Hoje')).toBeInTheDocument()
      expect(screen.getByText('Em Rota')).toBeInTheDocument()
      expect(screen.getByText('Ticket Médio')).toBeInTheDocument()
    })
  })

  it('renders financial summary', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Saldo em Caixa')).toBeInTheDocument()
      expect(screen.getByText('Recebido Hoje')).toBeInTheDocument()
      expect(screen.getByText('A Receber')).toBeInTheDocument()
      expect(screen.getByText('Resultado')).toBeInTheDocument()
    })
  })

  it('renders recent orders', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Pedidos Recentes')).toBeInTheDocument()
      expect(screen.getByText('#10482')).toBeInTheDocument()
      expect(screen.getByText('#10481')).toBeInTheDocument()
    })
  })

  it('renders alerts', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Alertas & Ações')).toBeInTheDocument()
      expect(screen.getByText('2 pedidos pendentes')).toBeInTheDocument()
    })
  })

  it('renders without crashing', async () => {
    const { container } = renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(container.firstChild).toBeTruthy()
    })
  })
})
