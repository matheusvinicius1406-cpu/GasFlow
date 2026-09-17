import { fireEvent, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { ThemeProvider } from '@/lib/theme/ThemeProvider'
import { MobileSidebar } from './MobileSidebar'

function renderDrawer(isOpen = true) {
  const onClose = vi.fn()
  const { container, unmount } = renderWithProviders(
    <ThemeProvider>
      <MobileSidebar isOpen={isOpen} onClose={onClose} />
    </ThemeProvider>,
  )
  return { onClose, container, unmount }
}

describe('MobileSidebar', () => {
  it('renders hidden when closed (wrapper hidden, dialog inacessível)', () => {
    const { container } = renderDrawer(false)
    // O drawer permanece montado, mas o wrapper esconde até md + aria-hidden
    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper.className).toContain('hidden')
    expect(wrapper).toHaveAttribute('aria-hidden', 'true')
    expect(screen.queryByRole('dialog', { hidden: false })).not.toBeInTheDocument()
  })

  it('renders as a modal dialog with all 7 nav groups', () => {
    renderDrawer(true)

    const dialog = screen.getByRole('dialog', { name: 'Menu de navegação' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')

    // 7 grupos da árvore v2 (Dashboard direto + 6 colapsáveis)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('WhatsApp')).toBeInTheDocument()
    expect(screen.getByText('Pedidos & Entregas')).toBeInTheDocument()
    expect(screen.getByText('Clientes')).toBeInTheDocument()
    expect(screen.getByText('Produtos & Estoque')).toBeInTheDocument()
    expect(screen.getByText('Financeiro & Relatórios')).toBeInTheDocument()
    expect(screen.getByText('Configurações')).toBeInTheDocument()
  })

  it('closes on Escape', () => {
    const { onClose } = renderDrawer(true)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes on backdrop click', () => {
    const { onClose, container } = renderDrawer(true)
    const backdrop = container.firstElementChild?.firstElementChild as HTMLElement
    fireEvent.click(backdrop)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes after navigating via a nav link', () => {
    const { onClose } = renderDrawer(true)
    fireEvent.click(screen.getByText('Dashboard'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('locks body scroll while open and restores on unmount', () => {
    const { unmount } = renderDrawer(true)
    expect(document.body.style.overflow).toBe('hidden')

    unmount()
    expect(document.body.style.overflow).toBe('')
  })
})
