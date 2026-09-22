/**
 * useTrackingSocket — posições do entregador por WebSocket (Fase 6).
 *
 * Assina o canal `tenant:{tenant_id}` reaproveitando o `useRealtime` existente
 * (mesmo /ws, mesma reconexão com backoff, mesmo heartbeat). Nada de hub
 * paralelo: o backend já roteia `driver.location_updated` para esse canal.
 *
 * Expõe:
 * - `pointsByDriver`: trajetos acumulados (para o polyline).
 * - `lastByDriver`: ponto mais recente por driver (marcador da moto).
 * - `isConnected` / `reconnectAttempts`: o pai decide o fallback (mantém o
 *   último estado do mapa quando o WS cai).
 */

import { useCallback, useMemo, useState } from 'react'
import { ACCESS_TOKEN_KEY } from '@/lib/api/session'
import { useRealtime } from '@/lib/hooks/useRealtime'
import {
  latestByDriver,
  mergeTrackingState,
  parseDriverAlertEvent,
  parseDriverLocationEvent,
  type DriverAlert,
  type TrackingState,
} from '@/lib/tracking'

export interface UseTrackingSocketOptions {
  /** Desliga a conexão (ex.: mapa fora da tela). */
  enabled?: boolean
  /** Janela do trajeto em minutos (default 30). */
  trailMinutes?: number
  /** Teto de pontos por trajeto (default 500). */
  maxPoints?: number
}

/** Teto de alertas mantidos em memória (os mais recentes). */
export const MAX_ALERTS = 20

export function useTrackingSocket({
  enabled = true,
  trailMinutes = 30,
  maxPoints = 500,
}: UseTrackingSocketOptions = {}) {
  const [pointsByDriver, setPointsByDriver] = useState<TrackingState>({})
  const [alerts, setAlerts] = useState<DriverAlert[]>([])

  const token = useMemo(() => {
    if (typeof window === 'undefined') return null
    return window.localStorage.getItem(ACCESS_TOKEN_KEY)
  }, [])

  const onEvent = useCallback(
    (message: unknown) => {
      // Fase 7.3: alertas operacionais (parado/desviado) do mesmo canal.
      const alert = parseDriverAlertEvent(message)
      if (alert) {
        setAlerts((prev) => [alert, ...prev].slice(0, MAX_ALERTS))
        return
      }

      const point = parseDriverLocationEvent(message)
      if (!point) return
      setPointsByDriver((prev) =>
        mergeTrackingState(prev, point, { maxPoints, windowMs: trailMinutes * 60_000 })
      )
    },
    [maxPoints, trailMinutes]
  )

  const { isConnected, reconnectAttempts } = useRealtime({
    token: enabled ? token : null,
    onEvent,
  })

  const lastByDriver = useMemo(() => latestByDriver(pointsByDriver), [pointsByDriver])
  const dismissAlert = useCallback((index = 0) => {
    setAlerts((prev) => prev.filter((_, i) => i !== index))
  }, [])

  return { pointsByDriver, lastByDriver, alerts, dismissAlert, isConnected, reconnectAttempts }
}
