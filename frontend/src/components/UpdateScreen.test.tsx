import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { ThemeProvider } from '@/lib/theme/ThemeProvider'
import { renderWithProviders } from '@/test/utils'
import type { UpdateState } from '@/lib/update/updater'
import { UpdateScreen } from './UpdateScreen'

/** Substitui a ponte do auto-update do Electron. */
function stubUpdater(initial: UpdateState) {
  const listeners = new Set<(state: UpdateState) => void>()

  const install = vi.fn(async () => ({ ok: true }))
  const api = {
    check: vi.fn(async () => ({ ok: true })),
    install,
    getState: vi.fn(async () => initial),
    onStateChange: vi.fn((cb: (state: UpdateState) => void) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    }),
  }

  window.gasflowUpdater = api
  return { api, install }
}

function renderScreen() {
  return renderWithProviders(
    <ThemeProvider>
      <UpdateScreen />
    </ThemeProvider>,
  )
}

const READY: UpdateState = { status: 'ready', version: '1.1.7', progress: 100, error: null }

afterEach(() => {
  delete window.gasflowUpdater
})

describe('UpdateScreen', () => {
  it('não renderiza nada fora do Electron', () => {
    renderScreen()

    expect(screen.queryByTestId('update-banner')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('mostra o progresso em banner, sem bloquear o app', async () => {
    stubUpdater({ status: 'downloading', version: '1.1.7', progress: 42, error: null })

    renderScreen()

    expect(await screen.findByTestId('update-banner')).toBeInTheDocument()
    expect(screen.getByText(/42%/)).toBeInTheDocument()
    // Banner não é modal: o usuário continua no app durante o download.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: /progresso do download/i })).toHaveAttribute(
      'aria-valuenow',
      '42',
    )
  })

  it('mostra barra indeterminada enquanto ainda não há percentual', async () => {
    stubUpdater({ status: 'available', version: '1.1.8', progress: 0, error: null })

    renderScreen()

    expect(await screen.findByText(/nova versão v1\.1\.8 disponível/i)).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: /progresso do download/i })).not.toHaveAttribute(
      'aria-valuenow',
    )
  })

  it('abre o overlay de decisão quando a versão está pronta', async () => {
    stubUpdater(READY)

    renderScreen()

    const dialog = await screen.findByRole('dialog', { name: /atualização pronta/i })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByText('v1.1.7')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reiniciar e instalar agora/i })).toBeInTheDocument()
  })

  it('instala e reinicia ao confirmar no overlay', async () => {
    const { install } = stubUpdater(READY)

    renderScreen()
    await screen.findByRole('dialog')

    fireEvent.click(screen.getByRole('button', { name: /reiniciar e instalar agora/i }))

    await waitFor(() => expect(install).toHaveBeenCalledTimes(1))
  })

  it('"Depois" rebaixa o aviso para banner, sem perder a atualização', async () => {
    stubUpdater(READY)

    renderScreen()
    await screen.findByRole('dialog')

    fireEvent.click(screen.getByRole('button', { name: 'Depois' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(await screen.findByTestId('update-banner')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reiniciar e instalar/i })).toBeInTheDocument()
  })

  it('Escape equivale a "Depois"', async () => {
    stubUpdater(READY)

    renderScreen()
    await screen.findByRole('dialog')

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('mostra a falha de instalação sem fechar a tela', async () => {
    const { api } = stubUpdater(READY)
    api.install = vi.fn(async () => ({ ok: false, error: 'Permissão negada pelo sistema.' }))

    renderScreen()
    await screen.findByRole('dialog')

    fireEvent.click(screen.getByRole('button', { name: /reiniciar e instalar agora/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Permissão negada pelo sistema.')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('não sobrepõe avisos: o banner de "pronta" só aparece após o adiamento', async () => {
    stubUpdater(READY)

    renderScreen()
    await screen.findByRole('dialog')

    // Enquanto o overlay está aberto, não há banner duplicado atrás dele.
    expect(screen.queryByTestId('update-banner')).not.toBeInTheDocument()
  })
})
