/**
 * Tracking — parsing e estado do mapa em tempo real (Fase 6).
 *
 * Funções puras (sem React/WebSocket) para poder testar sem tile real:
 * - `parseDriverLocationEvent`: envelope do /ws → ponto do entregador.
 * - `mergeTrackingState`: acumula o trajeto por driver (dedupe + ordenação +
 *   janela de tempo + teto de pontos), sem re-render do mapa inteiro.
 *
 * O backend publica `driver.location_updated` no canal `tenant:{id}` (barramento
 * existente). O nome em snake (`driver_location`) também é aceito para não
 * quebrar se o evento for renomeado no futuro.
 */

export interface DriverLocationUpdate {
  driver_id: string
  latitude: number
  longitude: number
  accuracy_m?: number | null
  speed_kmh?: number | null
  heading_deg?: number | null
  /** ISO-8601 — chave de dedupe/ordenação. */
  recorded_at: string
}

/** Trajetos por entregador: id → pontos ordenados por `recorded_at`. */
export type TrackingState = Record<string, DriverLocationUpdate[]>

export interface MergeOptions {
  /** Teto de pontos por trajeto (default 500). */
  maxPoints?: number
  /** Janela de tempo do trajeto em ms (default 30 min). */
  windowMs?: number
  /** "Agora" em ms — injetável para teste. */
  now?: number
}

const DEFAULT_MAX_POINTS = 500
const DEFAULT_WINDOW_MS = 30 * 60 * 1000

function numOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

/**
 * Extrai um ponto de um envelope do WebSocket. Retorna `null` para qualquer
 * mensagem que não seja um evento de posição válido (welcome, pong, stats,
 * eventos de entrega etc.) — o chamador simplesmente ignora.
 */
export function parseDriverLocationEvent(
  message: unknown
): DriverLocationUpdate | null {
  if (!message || typeof message !== 'object') return null
  const envelope = message as {
    type?: unknown
    event?: { type?: unknown; aggregate_id?: unknown; timestamp?: unknown; data?: Record<string, unknown> }
  }
  if (envelope.type !== 'event' || !envelope.event) return null

  const eventType = String(envelope.event.type ?? '')
  if (eventType !== 'driver.location_updated' && eventType !== 'driver_location') return null

  const data = envelope.event.data ?? {}
  const driverId = String(data.driver_id ?? envelope.event.aggregate_id ?? '')
  const latitude = numOrNull(data.latitude ?? data.lat)
  const longitude = numOrNull(data.longitude ?? data.lng)
  if (!driverId || latitude === null || longitude === null) return null

  return {
    driver_id: driverId,
    latitude,
    longitude,
    accuracy_m: numOrNull(data.accuracy_m ?? data.accuracy),
    speed_kmh: numOrNull(data.speed_kmh ?? data.speed),
    heading_deg: numOrNull(data.heading_deg ?? data.heading ?? data.bearing),
    recorded_at: String(data.recorded_at ?? envelope.event.timestamp ?? new Date().toISOString()),
  }
}

/**
 * Acrescenta um ponto ao trajeto: dedupe por `recorded_at`, mantém ordem
 * cronológica, descarta pontos fora da janela e corta no teto.
 */
export function appendPoint(
  trail: DriverLocationUpdate[],
  point: DriverLocationUpdate,
  options: MergeOptions = {}
): DriverLocationUpdate[] {
  if (trail.some((p) => p.recorded_at === point.recorded_at)) return trail

  const maxPoints = options.maxPoints ?? DEFAULT_MAX_POINTS
  const windowMs = options.windowMs ?? DEFAULT_WINDOW_MS
  const now = options.now ?? Date.now()

  let next = [...trail, point].sort((a, b) => a.recorded_at.localeCompare(b.recorded_at))

  // Janela deslizante (só aplica quando `recorded_at` é parseável).
  const cutoff = now - windowMs
  const parsed = next.map((p) => {
    const t = Date.parse(p.recorded_at)
    return { p, t }
  })
  if (parsed.every(({ t }) => Number.isFinite(t))) {
    next = parsed.filter(({ t }) => t >= cutoff).map(({ p }) => p)
  }

  return next.length > maxPoints ? next.slice(next.length - maxPoints) : next
}

/** Estado novo (imutável) com o ponto aplicado ao trajeto do seu driver. */
export function mergeTrackingState(
  state: TrackingState,
  point: DriverLocationUpdate,
  options: MergeOptions = {}
): TrackingState {
  const trail = state[point.driver_id] ?? []
  const nextTrail = appendPoint(trail, point, options)
  if (nextTrail === trail) return state
  return { ...state, [point.driver_id]: nextTrail }
}

/**
 * Alerta operacional publicado pelo backend (`driver.alert`, Fase 7.3).
 */
export interface DriverAlert {
  kind: 'STALLED' | 'DEVIATED'
  driver_id: string
  delivery_id?: string | null
  minutes?: number
  deviation_km?: number
  moved_m?: number
}

/** Extrai um `driver.alert` do envelope do WebSocket (ou `null`). */
export function parseDriverAlertEvent(message: unknown): DriverAlert | null {
  if (!message || typeof message !== 'object') return null
  const envelope = message as {
    type?: unknown
    event?: { type?: unknown; aggregate_id?: unknown; data?: Record<string, unknown> }
  }
  if (envelope.type !== 'event' || !envelope.event) return null
  if (String(envelope.event.type ?? '') !== 'driver.alert') return null

  const data = envelope.event.data ?? {}
  const kind = String(data.kind ?? '')
  const driverId = String(data.driver_id ?? envelope.event.aggregate_id ?? '')
  if (!driverId || (kind !== 'STALLED' && kind !== 'DEVIATED')) return null

  return {
    kind,
    driver_id: driverId,
    delivery_id: data.delivery_id ? String(data.delivery_id) : null,
    minutes: numOrNull(data.minutes) ?? undefined,
    deviation_km: numOrNull(data.deviation_km) ?? undefined,
    moved_m: numOrNull(data.moved_m) ?? undefined,
  }
}

/** Ponto mais recente de cada trajeto. */
export function latestByDriver(
  state: TrackingState
): Record<string, DriverLocationUpdate> {
  const out: Record<string, DriverLocationUpdate> = {}
  for (const [driverId, trail] of Object.entries(state)) {
    const last = trail[trail.length - 1]
    if (last) out[driverId] = last
  }
  return out
}

/**
 * Rota otimizada por entregador (Fase 8). Recebida pelo WebSocket quando o
 * operador ou o gatilho automático reordena a rota do entregador.
 */
export interface OptimizedRoute {
  driver_id: string
  ordered_delivery_ids: string[]
  geometry: [number, number][] | null
  improvement_km: number
  provider: string
  changed: boolean
}

/** Extrai um `route.optimized` do envelope do WebSocket (ou `null`). */
export function parseRouteOptimizedEvent(
  message: unknown
): OptimizedRoute | null {
  if (!message || typeof message !== 'object') return null
  const envelope = message as {
    type?: unknown
    event?: { type?: unknown; aggregate_id?: unknown; data?: Record<string, unknown> }
  }
  if (envelope.type !== 'event' || !envelope.event) return null
  if (String(envelope.event.type ?? '') !== 'route.optimized') return null

  const data = envelope.event.data ?? {}
  const driverId = String(data.driver_id ?? envelope.event.aggregate_id ?? '')
  const ids = data.ordered_delivery_ids
  if (!driverId || !Array.isArray(ids)) return null

  return {
    driver_id: driverId,
    ordered_delivery_ids: ids.map(String),
    geometry: Array.isArray(data.geometry)
      ? (data.geometry as [number, number][])
      : null,
    improvement_km: numOrNull(data.improvement_km) ?? 0,
    provider: String(data.provider ?? 'unknown'),
    changed: Boolean(data.changed),
  }
}
