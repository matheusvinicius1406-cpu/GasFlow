/**
 * Realtime helpers — shared by useRealtime and RealtimeBridge.
 *
 * The backend pushes Domain Events (delivery and driver lifecycle events)
 * over the tenant WebSocket channel. The bridge translates those events into React Query
 * invalidations so list pages (Deliveries, Dashboard) refresh on change.
 */

/** Message envelope sent by the backend over /ws. */
export interface RealtimeServerMessage {
  type: 'connected' | 'pong' | 'stats' | 'event'
  channel?: string
  timestamp?: string
  event?: {
    type: string
    tenant_id?: string
    aggregate_id?: string
    actor_type?: string
    data?: Record<string, unknown>
    [key: string]: unknown
  }
  [key: string]: unknown
}

/**
 * Map a domain event type to the React Query keys that must be invalidated.
 * Pure function — unit-testable without a WebSocket.
 *
 * - delivery.* events change deliveries, the dispatch summary and orders.
 * - driver availability changes the driver list and dispatch summary.
 * - driver.location_updated is intentionally ignored: it is high-frequency
 *   and no current screen renders live positions (would cause refetch storms).
 */
export function realtimeQueryKeys(eventType: string): string[][] {
  if (eventType.startsWith('delivery.')) {
    return [['deliveries'], ['delivery-summary'], ['delivery-drivers'], ['dashboard'], ['orders']]
  }
  if (eventType === 'driver.available' || eventType === 'driver.unavailable' || eventType === 'driver.paused') {
    return [['delivery-drivers'], ['delivery-summary'], ['dashboard']]
  }
  return []
}

/** Whether a domain event type is relevant to the operator dashboard. */
export function isRelevantEvent(message: RealtimeServerMessage): boolean {
  return message?.type === 'event' && !!message.event?.type
}

/**
 * Build the WebSocket URL for the current origin.
 * The backend derives the tenant channel from the JWT token, so the client
 * only needs to pass the token (dev/prod proxies forward /ws unrewritten).
 */
export function buildRealtimeUrl(token: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const params = new URLSearchParams({ token })
  return `${proto}://${window.location.host}/ws?${params.toString()}`
}
