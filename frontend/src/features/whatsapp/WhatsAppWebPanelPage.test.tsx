import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { WhatsAppWebPanelPage } from './WhatsAppWebPanelPage'

/**
 * Testes da moldura React (F1–F3): abas por conta, status bridge,
 * flag off, e estado sem ponte desktop (navegador puro).
 */

type StatusListener = (status: { accountId: string; state: string; lastEventAt: string | null; lastError: string | null }) => void

function makeBridge(overrides: Partial<Record<string, unknown>> = {}) {
  const listeners: StatusListener[] = []
  return {
    listeners,
    bridge: {
      waWebStatuses: vi.fn(async () => ({
        ok: true,
        enabled: true,
        statuses: [
          { accountId: 'primary', state: 'connected', lastEventAt: '2026-09-14T10:00:00Z', lastError: null },
          { accountId: 'secondary', state: 'closed', lastEventAt: null, lastError: null },
        ],
      })),
      waWebShow: vi.fn(async () => ({ ok: true })),
      waWebBounds: vi.fn(async () => ({ ok: true })),
      waWebHide: vi.fn(async () => ({ ok: true })),
      waWebRePair: vi.fn(async () => ({ ok: true })),
      waWebClose: vi.fn(async () => ({ ok: true })),
      onWaWebStatus: vi.fn((cb: StatusListener) => {
        listeners.push(cb)
        return () => {
          const i = listeners.indexOf(cb)
          if (i >= 0) listeners.splice(i, 1)
        }
      }),
      ...overrides,
    },
  }
}

function setBridge(bridge: unknown) {
  ;(window as unknown as { gasflow?: unknown }).gasflow = bridge
}

describe('WhatsAppWebPanelPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setBridge(undefined)
    // ResizeObserver não existe no jsdom
    ;(window as unknown as { ResizeObserver?: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    // getBoundingClientRect do jsdom retorna zeros — stub com área real
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      x: 10,
      y: 10,
      width: 800,
      height: 480,
      top: 10,
      left: 10,
      right: 810,
      bottom: 490,
      toJSON: () => ({}),
    } as DOMRect)
  })

  it('shows the desktop-only message when there is no bridge', () => {
    render(<WhatsAppWebPanelPage />)
    expect(screen.getByText(/só está disponível no aplicativo desktop/i)).toBeInTheDocument()
  })

  it('shows the disabled message when the flag is off', async () => {
    const { bridge } = makeBridge({
      waWebStatuses: vi.fn(async () => ({ ok: true, enabled: false, statuses: [] })),
    })
    setBridge(bridge)
    render(<WhatsAppWebPanelPage />)
    await waitFor(() => {
      expect(screen.getByText(/desativado nas configurações/i)).toBeInTheDocument()
    })
  })

  it('renders account tabs with status dots and pushes statuses live', async () => {
    const { bridge, listeners } = makeBridge()
    setBridge(bridge)
    render(<WhatsAppWebPanelPage />)

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /principal/i })).toHaveAttribute('aria-selected', 'true')
    })
    // Estado inicial carregado
    expect(screen.getByText('Conectado')).toBeInTheDocument()

    // F3 — push view → main → React reflete o novo estado
    act(() => {
      listeners.forEach((cb) => cb({ accountId: 'secondary', state: 'qr', lastEventAt: '2026-09-14T10:01:00Z', lastError: null }))
    })
    fireEvent.click(screen.getByRole('tab', { name: /secundária/i }))
    expect(screen.getByText('Aguardando QR')).toBeInTheDocument()
  })

  it('opens the panel with placeholder bounds for the active account', async () => {
    const { bridge } = makeBridge()
    setBridge(bridge)
    render(<WhatsAppWebPanelPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: /abrir painel/i })).toBeEnabled())

    fireEvent.click(screen.getByRole('button', { name: /abrir painel/i }))
    await waitFor(() => {
      expect(bridge.waWebShow).toHaveBeenCalledWith('primary', { x: 10, y: 10, width: 800, height: 480 })
    })
  })

  it('re-pair and close call the bridge for the active account', async () => {
    const { bridge } = makeBridge()
    setBridge(bridge)
    render(<WhatsAppWebPanelPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: /re-parear/i })).toBeEnabled())

    fireEvent.click(screen.getByRole('button', { name: /re-parear/i }))
    await waitFor(() => expect(bridge.waWebRePair).toHaveBeenCalledWith('primary'))

    fireEvent.click(screen.getByRole('button', { name: /^fechar$/i }))
    await waitFor(() => expect(bridge.waWebClose).toHaveBeenCalledWith('primary'))
  })
})
