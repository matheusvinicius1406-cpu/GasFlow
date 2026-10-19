import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ErrorState } from './ErrorState'

describe('ErrorState', () => {
  it('sem falha classificada mantém o título genérico', () => {
    render(<ErrorState message="Não foi possível carregar os usuários." />)
    expect(screen.getByText('Algo deu errado')).toBeInTheDocument()
  })

  it('403 vira "Sem permissão"', () => {
    render(
      <ErrorState
        error={{ response: { status: 403 } }}
        message="Não foi possível carregar os usuários."
      />
    )
    expect(screen.getByText('Sem permissão')).toBeInTheDocument()
    expect(screen.getByText('Não foi possível carregar os usuários.')).toBeInTheDocument()
  })

  it('falha de transporte vira "Sem conexão"', () => {
    render(<ErrorState error={new Error('Network Error')} message="Não foi possível carregar." />)
    expect(screen.getByText('Sem conexão')).toBeInTheDocument()
  })

  it('500 mantém o genérico', () => {
    render(<ErrorState error={{ response: { status: 500 } }} message="Falhou." />)
    expect(screen.getByText('Algo deu errado')).toBeInTheDocument()
  })

  it('título explícito vence a classificação', () => {
    render(<ErrorState title="Falha crítica" error={{ response: { status: 403 } }} message="x" />)
    expect(screen.getByText('Falha crítica')).toBeInTheDocument()
    expect(screen.queryByText('Sem permissão')).not.toBeInTheDocument()
  })

  it('erro nulo não muda o título', () => {
    render(<ErrorState error={null} message="Falhou." />)
    expect(screen.getByText('Algo deu errado')).toBeInTheDocument()
  })

  it('mostra o botão de retry quando há onRetry', () => {
    const onRetry = vi.fn()
    render(<ErrorState message="Erro" onRetry={onRetry} />)
    screen.getByText('Tentar novamente').click()
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
