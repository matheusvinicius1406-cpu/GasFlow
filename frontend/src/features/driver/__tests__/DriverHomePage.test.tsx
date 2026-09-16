/**
 * DriverHomePage — F1a: notificação de atribuição via realtime.
 *
 * Fluxo testado: evento `delivery.assigned` chega pelo canal WS do motorista
 * → useNotifySound.play() + toast visível + refetch das entregas.
 * useRealtime é mockado para capturar o callback onEvent injetado pelo
 * componente; fetch é mockado para as chamadas /driver/*.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { DriverHomePage } from '../DriverHomePage'

// Captura o onEvent que o componente registra no canal realtime.
let capturedOnEvent: ((message: unknown) => void) | null = null

// Referência estável do play (vi.mock factory é hoisted — usar vi.hoisted).
const { playMock } = vi.hoisted(() => ({ playMock: vi.fn() }))

vi.mock('@/lib/hooks/useRealtime', () => ({
  useRealtime: vi.fn((options: { onEvent?: (message: unknown) => void }) => {
    capturedOnEvent = options?.onEvent ?? null
    return { isConnected: true, reconnectAttempts: 0 }
  }),
}))

vi.mock('@/lib/hooks/useNotifySound', () => ({
  useNotifySound: () => ({ play: playMock, unlock: vi.fn() }),
}))

const deliveriesResponse = {
  deliveries: [
    {
      delivery_id: 'd1',
      order_reference: 'P-1',
      customer_name: 'Maria',
      address: 'Rua A, 123',
      status: 'ASSIGNED',
      scheduled_at: null,
      version: 1,
    },
  ],
}

const fetchMock = vi.fn((url: string) => {
  if (url.includes('/driver/deliveries')) {
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(deliveriesResponse) })
  }
  if (url.includes('/driver/me')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ driver_id: '654321', name: 'João', status: 'AVAILABLE', tracking_interval_seconds: 120 }),
    })
  }
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/driver']}>
      <DriverHomePage />
    </MemoryRouter>
  )
}

describe('DriverHomePage — notificação de atribuição (F1a)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    capturedOnEvent = null
    window.localStorage.setItem('driver_token', 'test-token')
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)
  })

  afterEach(() => {
    window.localStorage.clear()
    vi.unstubAllGlobals()
    cleanup()
  })

  it('delivery.assigned → toca som, mostra toast e refetcha entregas', async () => {
    renderPage()

    // Hook registrou callback de realtime
    await waitFor(() => expect(capturedOnEvent).not.toBeNull())
    // Entrega inicial carregada
    await waitFor(() => expect(screen.getByText('Maria')).toBeInTheDocument())

    // Zera contagem de fetch antes do evento (chamadas de mount já aconteceram)
    fetchMock.mockClear()

    act(() => {
      capturedOnEvent?.({
        type: 'event',
        event: { type: 'delivery.assigned', tenant_id: 'default', aggregate_id: 'd1', actor_id: '654321', actor_type: 'DRIVER', data: {} },
      })
    })

    expect(playMock).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(/Nova entrega atribuída/i)).toBeInTheDocument()

    // refetch das entregas após o evento
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/driver/deliveries'))).toBe(true)
    })
  })

  it('eventos irrelevantes não disparam notificação', async () => {
    renderPage()
    await waitFor(() => expect(capturedOnEvent).not.toBeNull())
    await waitFor(() => expect(screen.getByText('Maria')).toBeInTheDocument())

    fetchMock.mockClear()
    act(() => {
      capturedOnEvent?.({ type: 'event', event: { type: 'delivery.completed', data: {} } })
    })

    expect(playMock).not.toHaveBeenCalled()
    expect(screen.queryByText(/Nova entrega atribuída/i)).not.toBeInTheDocument()
  })
})
