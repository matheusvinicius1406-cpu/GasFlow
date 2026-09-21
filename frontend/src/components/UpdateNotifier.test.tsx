import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { ThemeProvider } from '@/lib/theme/ThemeProvider'
import { renderWithProviders } from '@/test/utils'
import type { UpdateState } from '@/lib/update/updater'
import { UpdateNotifier } from './UpdateNotifier'

function stubUpdater(initial: UpdateState) {
  const api = {
    check: vi.fn(async () => ({ ok: true })),
    install: vi.fn(async () => ({ ok: true })),
    getState: vi.fn(async () => initial),
    onStateChange: vi.fn(() => () => undefined),
  }
  window.gasflowUpdater = api
  return api
}

function renderNotifier() {
  return renderWithProviders(
    <ThemeProvider>
      <UpdateNotifier />
    </ThemeProvider>,
  )
}

afterEach(() => {
  delete window.gasflowUpdater
})

describe('UpdateNotifier', () => {
  it('não renderiza fora do Electron', () => {
    renderNotifier()
    expect(screen.queryByTestId('update-notifier')).not.toBeInTheDocument()
  })

  it('avisa que está verificando', async () => {
    stubUpdater({ status: 'checking', version: null, progress: 0, error: null })

    renderNotifier()

    expect(await screen.findByText(/verificando atualizações/i)).toBeInTheDocument()
  })

  it('avisa falha de verificação', async () => {
    stubUpdater({ status: 'error', version: null, progress: 0, error: 'offline' })

    renderNotifier()

    expect(await screen.findByText(/falha ao verificar atualizações/i)).toBeInTheDocument()
  })

  it('permite tentar a verificação de novo depois de uma falha', async () => {
    const api = stubUpdater({ status: 'error', version: null, progress: 0, error: 'offline' })

    renderNotifier()
    await screen.findByText(/falha ao verificar atualizações/i)

    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }))

    await waitFor(() => expect(api.check).toHaveBeenCalledTimes(1))
  })

  it('sai de cena nos estados que pertencem ao UpdateScreen', async () => {
    const api = stubUpdater({ status: 'downloading', version: '1.1.7', progress: 10, error: null })

    renderNotifier()

    // Espera o estado assíncrono da ponte chegar para então conferir a ausência.
    await waitFor(() => expect(api.getState).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByTestId('update-notifier')).not.toBeInTheDocument())
  })
})
