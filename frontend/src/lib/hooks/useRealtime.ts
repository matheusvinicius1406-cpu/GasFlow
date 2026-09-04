import { useEffect, useRef, useState, useCallback } from 'react'
import { buildRealtimeUrl, type RealtimeServerMessage } from '@/lib/realtime'

interface UseRealtimeOptions {
  token: string | null
  /** Milliseconds between reconnection attempts (grows by factor each try). */
  reconnectBaseDelay?: number
  maxReconnectAttempts?: number
  onEvent?: (message: RealtimeServerMessage) => void
}

interface UseRealtimeResult {
  isConnected: boolean
  reconnectAttempts: number
}

const HEARTBEAT_INTERVAL_MS = 25_000

/**
 * Connect to the backend /ws tenant channel and keep the connection alive.
 *
 * - Auto-reconnects with exponential backoff (capped at maxReconnectAttempts).
 * - Sends "ping" every 25s so proxies do not idle-timeout the socket.
 * - `onEvent` receives parsed server messages (delivery and driver events).
 */
export function useRealtime({
  token,
  reconnectBaseDelay = 1000,
  maxReconnectAttempts = 10,
  onEvent,
}: UseRealtimeOptions): UseRealtimeResult {
  const [isConnected, setIsConnected] = useState(false)
  const [reconnectAttempts, setReconnectAttempts] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onEventRef = useRef(onEvent)

  useEffect(() => {
    onEventRef.current = onEvent
  }, [onEvent])

  const cleanup = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current)
      heartbeatRef.current = null
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      wsRef.current.onmessage = null
      wsRef.current.onopen = null
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const startHeartbeat = useCallback((ws: WebSocket) => {
    if (heartbeatRef.current) clearInterval(heartbeatRef.current)
    heartbeatRef.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }, HEARTBEAT_INTERVAL_MS)
  }, [])

  useEffect(() => {
    if (!token) {
      setIsConnected(false)
      return
    }

    let disposed = false

    const connect = (attempt: number) => {
      if (disposed) return

      let ws: WebSocket
      try {
        ws = new WebSocket(buildRealtimeUrl(token))
      } catch {
        // URL construction or browser restriction — do not retry loop here
        return
      }
      wsRef.current = ws

      ws.onopen = () => {
        if (disposed) return
        setIsConnected(true)
        setReconnectAttempts(0)
        startHeartbeat(ws)
      }

      ws.onmessage = (event: MessageEvent) => {
        if (disposed) return
        try {
          const data = JSON.parse(String(event.data)) as RealtimeServerMessage
          onEventRef.current?.(data)
        } catch {
          // Non-JSON message (e.g. raw pong) — ignore
        }
      }

      ws.onclose = () => {
        if (disposed) return
        setIsConnected(false)
        if (heartbeatRef.current) {
          clearInterval(heartbeatRef.current)
          heartbeatRef.current = null
        }
        // Reconnect with exponential backoff
        const next = attempt + 1
        if (next <= maxReconnectAttempts) {
          setReconnectAttempts(next)
          const delay = reconnectBaseDelay * Math.min(2 ** (next - 1), 30)
          reconnectTimerRef.current = setTimeout(() => connect(next), delay)
        }
      }

      ws.onerror = () => {
        // onclose follows; close() triggers reconnect logic above
        try {
          ws.close()
        } catch {
          // already closed
        }
      }
    }

    connect(0)

    return () => {
      disposed = true
      cleanup()
      setIsConnected(false)
    }
  }, [token, reconnectBaseDelay, maxReconnectAttempts, cleanup])

  return { isConnected, reconnectAttempts }
}
