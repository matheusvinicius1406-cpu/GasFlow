import { fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { CentralFinanceiraPage } from '../CentralFinanceiraPage'
import { SectionShell } from '../SectionShell'
import { SECTIONS } from '../usePeriodFilter'

function abaGroup() {
  return screen.getByRole('group', { name: 'Seções da Central Financeira' })
}

function presetGroup() {
  return screen.getByRole('group', { name: 'Período da Central Financeira' })
}

describe('CentralFinanceiraPage (P4 — shell)', () => {
  it('renderiza título e as 15 abas das seções', () => {
    renderWithProviders(<CentralFinanceiraPage />)
    expect(screen.getByRole('heading', { name: 'Central Financeira' })).toBeInTheDocument()
    expect(within(abaGroup()).getAllByRole('button')).toHaveLength(SECTIONS.length)
    expect(SECTIONS).toHaveLength(15)
  })

  it('presets V1 (Hoje/7/30/90/180) com 30 dias ativo por padrão', () => {
    renderWithProviders(<CentralFinanceiraPage />)
    const grupo = presetGroup()
    for (const nome of ['Hoje', '7 dias', '30 dias', '90 dias', '180 dias']) {
      expect(within(grupo).getByRole('button', { name: nome })).toBeInTheDocument()
    }
    expect(within(grupo).getByRole('button', { name: '30 dias' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(grupo).getByRole('button', { name: '180 dias' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('trocar o preset marca o novo período', () => {
    renderWithProviders(<CentralFinanceiraPage />)
    fireEvent.click(within(presetGroup()).getByRole('button', { name: '180 dias' }))
    expect(within(presetGroup()).getByRole('button', { name: '180 dias' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(presetGroup()).getByRole('button', { name: '30 dias' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('aba padrão é Visão Geral (placeholder do P5) e trocar de aba muda a seção', () => {
    renderWithProviders(<CentralFinanceiraPage />)
    expect(screen.getByRole('heading', { name: 'Visão Geral — em construção' })).toBeInTheDocument()
    expect(screen.getByText(/PR P5 da Central Financeira/)).toBeInTheDocument()

    fireEvent.click(within(abaGroup()).getByRole('button', { name: 'DRE' }))
    expect(screen.getByRole('heading', { name: 'DRE — em construção' })).toBeInTheDocument()
    expect(screen.getByText(/PR P6 da Central Financeira/)).toBeInTheDocument()
  })

  it('respeita o deep-link ?secao=', () => {
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance/central?secao=mapa-de-calor' })
    expect(screen.getByRole('heading', { name: 'Mapa de Calor — em construção' })).toBeInTheDocument()
    expect(within(abaGroup()).getByRole('button', { name: 'Mapa de Calor' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('seção desconhecida na URL cai na padrão (visao-geral)', () => {
    renderWithProviders(<CentralFinanceiraPage />, { route: '/finance/central?secao=inexistente' })
    expect(screen.getByRole('heading', { name: 'Visão Geral — em construção' })).toBeInTheDocument()
  })
})

describe('SectionShell', () => {
  it('mostra loading', () => {
    const { container } = renderWithProviders(<SectionShell title="T" loading />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('mostra erro com retry', () => {
    renderWithProviders(<SectionShell title="T" error onRetry={() => {}} />)
    expect(screen.getByText('Não foi possível carregar os dados.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('mostra empty state', () => {
    renderWithProviders(<SectionShell title="T" empty emptyTitle="Vazio aqui" emptyDescription="Nada." />)
    expect(screen.getByRole('heading', { name: 'Vazio aqui' })).toBeInTheDocument()
    expect(screen.getByText('Nada.')).toBeInTheDocument()
  })
})
