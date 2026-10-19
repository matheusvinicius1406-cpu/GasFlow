import { screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { PERMISSION_DENIED_TITLE, PermissionDenied } from './PermissionDenied'

describe('PermissionDenied', () => {
  it('mostra o título único de permissão negada', () => {
    renderWithProviders(<PermissionDenied />)
    expect(
      screen.getByRole('heading', { name: PERMISSION_DENIED_TITLE })
    ).toBeInTheDocument()
    expect(screen.getByText('Seu usuário não tem acesso a esta área.')).toBeInTheDocument()
  })

  it('oferece a saída para o início', () => {
    renderWithProviders(<PermissionDenied />)
    expect(screen.getByRole('link', { name: 'Ir para o início' })).toBeInTheDocument()
  })

  it('aceita descrição própria', () => {
    renderWithProviders(<PermissionDenied description="Falta finance.read." />)
    expect(screen.getByText('Falta finance.read.')).toBeInTheDocument()
  })
})
