// Tests for UI components used in Orders domain
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import { Package } from 'lucide-react'

// === StatusBadge Tests ===

import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('renders PENDING status', () => {
    render(<StatusBadge status="PENDING" />)
    expect(screen.getByText('Novo')).toBeInTheDocument()
  })

  it('renders CONFIRMED status', () => {
    render(<StatusBadge status="CONFIRMED" />)
    expect(screen.getByText('Confirmado')).toBeInTheDocument()
  })

  it('renders PREPARING status', () => {
    render(<StatusBadge status="PREPARING" />)
    expect(screen.getByText('Em preparação')).toBeInTheDocument()
  })

  it('renders DELIVERING status', () => {
    render(<StatusBadge status="DELIVERING" />)
    expect(screen.getByText('Em entrega')).toBeInTheDocument()
  })

  it('renders DELIVERED status', () => {
    render(<StatusBadge status="DELIVERED" />)
    expect(screen.getByText('Entregue')).toBeInTheDocument()
  })

  it('renders CANCELLED status', () => {
    render(<StatusBadge status="CANCELLED" />)
    expect(screen.getByText('Cancelado')).toBeInTheDocument()
  })

  it('renders unknown status gracefully', () => {
    render(<StatusBadge status="UNKNOWN" />)
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument()
  })
})

// === StatCard Tests ===

import { StatCard } from './StatCard'

describe('StatCard', () => {
  it('renders title and value with icon', () => {
    render(
      <StatCard title="Vendas Hoje" value="R$ 1.500,00" icon={Package} />
    )
    expect(screen.getByText('Vendas Hoje')).toBeInTheDocument()
    expect(screen.getByText('R$ 1.500,00')).toBeInTheDocument()
  })

  it('renders with description', () => {
    render(
      <StatCard
        title="Pedidos"
        value="12"
        icon={Package}
        description="últimas 24h"
      />
    )
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('últimas 24h')).toBeInTheDocument()
  })

  it('renders with positive trend', () => {
    render(
      <StatCard
        title="Entregas"
        value="8"
        icon={Package}
        trend={{ value: 15, isPositive: true }}
      />
    )
    expect(screen.getByText('+15%')).toBeInTheDocument()
  })

  it('renders with negative trend', () => {
    render(
      <StatCard
        title="Cancelamentos"
        value="2"
        icon={Package}
        trend={{ value: 10, isPositive: false }}
      />
    )
    expect(screen.getByText('10%')).toBeInTheDocument()
  })
})

// === EmptyState Tests ===

import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('renders title and description with icon', () => {
    render(
      <EmptyState
        icon={Package}
        title="Nenhum pedido"
        description="Crie seu primeiro pedido"
      />
    )
    expect(screen.getByText('Nenhum pedido')).toBeInTheDocument()
    expect(screen.getByText('Crie seu primeiro pedido')).toBeInTheDocument()
  })

  it('renders action when provided as ReactNode', () => {
    render(
      <EmptyState
        icon={Package}
        title="Nenhum pedido"
        description="Crie seu primeiro pedido"
        action={<button>Criar Pedido</button>}
      />
    )
    const button = screen.getByText('Criar Pedido')
    expect(button).toBeInTheDocument()
    button.click()
  })
})

// === LoadingSpinner Tests ===

import { LoadingSpinner, LoadingPage } from './LoadingSpinner'

describe('LoadingSpinner', () => {
  it('renders spinner with default size', () => {
    const { container } = render(<LoadingSpinner />)
    const spinner = container.firstChild as HTMLElement
    expect(spinner).toHaveClass('animate-spin')
  })

  it('renders with custom size', () => {
    const { container } = render(<LoadingSpinner size="lg" />)
    const spinner = container.firstChild as HTMLElement
    expect(spinner).toHaveClass('h-12')
  })
})

describe('LoadingPage', () => {
  it('renders centered page', () => {
    const { container } = render(<LoadingPage />)
    expect(container.firstChild).toBeTruthy()
  })
})

// === ErrorState Tests ===

import { ErrorState } from './ErrorState'

describe('ErrorState', () => {
  it('renders error message', () => {
    render(<ErrorState message="Erro ao carregar pedidos" />)
    expect(screen.getByText('Erro ao carregar pedidos')).toBeInTheDocument()
  })

  it('renders default title', () => {
    render(<ErrorState message="Algo falhou" />)
    expect(screen.getByText('Algo deu errado')).toBeInTheDocument()
  })

  it('renders custom title', () => {
    render(<ErrorState title="Falha crítica" message="Erro de conexão" />)
    expect(screen.getByText('Falha crítica')).toBeInTheDocument()
  })

  it('renders retry button when onRetry provided', () => {
    const onRetry = vi.fn()
    render(<ErrorState message="Erro" onRetry={onRetry} />)
    const button = screen.getByText('Tentar novamente')
    button.click()
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('does not render retry button without onRetry', () => {
    render(<ErrorState message="Erro" />)
    expect(screen.queryByText('Tentar novamente')).not.toBeInTheDocument()
  })
})
