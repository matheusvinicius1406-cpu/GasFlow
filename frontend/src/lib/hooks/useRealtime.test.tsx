import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useRealtime } from './useRealtime'

/**
 * Minimal WebSocket stub for jsdom (no native WebSocket).
 * Emulates the browser API surface the hook uses.
 */
class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static OPEN = 1
  static CONNECTING = 0
  static CLOSED = 3

  static reset() {
    FakeWebSocket.instances = []
  }

  url: string
  readyState = FakeWebSocket.CONNECTING
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED
  }

  // Test helpers — simulate server behavior
  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  receive(json: unknown) {
    this.onmessage?.({ data: JSON.stringify(json) })
  }

  closeFromServer() {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.()
  }
}

// jsdom does not implement WebSocket
vi.stubGlobal('WebSocket', FakeWebSocket)

describe('useRealtime', () => {
  beforeEach(() => {
    FakeWebSocket.reset()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  it('does not connect without a token', () => {
    renderHook(() => useRealtime({ token: null }))
    expect(FakeWebSocket.instances.length).toBe(0)
  })

  it('connects with the token and reports connected state', async () => {
    const { result } = renderHook(() => useRealtime({ token: 'tok-1' }))
    expect(FakeWebSocket.instances.length).toBe(1)
    expect(FakeWebSocket.instances[0]!.url).toContain('token=tok-1')

    act(() => {
      FakeWebSocket.instances[0]!.open()
    })
    expect(result.current.isConnected).toBe(true)
  })

  it('delivers parsed events to onEvent', () => {
    const onEvent = vi.fn()
    renderHook(() => useRealtime({ token: 'tok-1', onEvent }))

    act(() => {
      const ws = FakeWebSocket.instances[0]!
      ws.open()
      ws.receive({ type: 'event', event: { type: 'delivery.completed' } })
    })

    expect(onEvent).toHaveBeenCalledTimes(1)
    const msg = onEvent.mock.calls[0]![0] as { event: { type: string } }
    expect(msg.event.type).toBe('delivery.completed')
  })

  it('reconnects after the socket closes', async () => {
    const { result } = renderHook(() =>
      useRealtime({ token: 'tok-1', reconnectBaseDelay: 100 })
    )
    act(() => {
      FakeWebSocket.instances[0]!.open()
    })
    expect(result.current.isConnected).toBe(true)

    act(() => {
      FakeWebSocket.instances[0]!.closeFromServer()
    })
    expect(result.current.isConnected).toBe(false)
    expect(result.current.reconnectAttempts).toBe(1)

    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(FakeWebSocket.instances.length).toBe(2)
  })

  it('disconnects cleanly on unmount', () => {
    const { unmount } = renderHook(() => useRealtime({ token: 'tok-1' }))
    const ws = FakeWebSocket.instances[0]!
    const closeSpy = vi.spyOn(ws, 'close')

    unmount()
    expect(closeSpy).toHaveBeenCalled()
  })

  it('sends heartbeat pings while connected', async () => {
    renderHook(() => useRealtime({ token: 'tok-1' }))
    act(() => {
      FakeWebSocket.instances[0]!.open()
    })

    act(() => {
      vi.advanceTimersByTime(25_000)
    })
    expect(FakeWebSocket.instances[0]!.sent).toContain('ping')
  })
})
