/**
 * tracking — Fase 6 (parser + estado do mapa em tempo real).
 *
 * Testes puros: sem WebSocket, sem tile, sem DOM. Cobrem o contrato do evento
 * `driver.location_updated` do backend e as regras de merge do trajeto
 * (dedupe, ordenação, janela e teto).
 */
import { describe, it, expect } from 'vitest'
import {
  appendPoint,
  latestByDriver,
  mergeTrackingState,
  parseDriverAlertEvent,
  parseDriverLocationEvent,
  type DriverLocationUpdate,
} from './tracking'

function event(data: Record<string, unknown>, type = 'driver.location_updated') {
  return {
    type: 'event',
    channel: 'tenant:t1',
    event: { type, tenant_id: 't1', aggregate_id: 'drv1', timestamp: '2026-09-22T12:00:00Z', data },
  }
}

function point(over: Partial<DriverLocationUpdate> = {}): DriverLocationUpdate {
  return {
    driver_id: 'drv1',
    latitude: -23.55,
    longitude: -46.63,
    accuracy_m: 10,
    speed_kmh: 30,
    heading_deg: 90,
    recorded_at: '2026-09-22T12:00:00Z',
    ...over,
  }
}

describe('parseDriverLocationEvent', () => {
  it('extrai o ponto do envelope driver.location_updated', () => {
    const parsed = parseDriverLocationEvent(
      event({ driver_id: 'drv1', latitude: -23.55, longitude: -46.63, speed_kmh: 42, recorded_at: '2026-09-22T12:00:00Z' })
    )
    expect(parsed).toMatchObject({ driver_id: 'drv1', latitude: -23.55, longitude: -46.63, speed_kmh: 42 })
  })

  it('aceita o alias snake_case driver_location', () => {
    const parsed = parseDriverLocationEvent(event({ latitude: -1, longitude: -48 }, 'driver_location'))
    expect(parsed?.driver_id).toBe('drv1')
  })

  it('ignora welcome/pong/stats e eventos que não são de posição', () => {
    expect(parseDriverLocationEvent({ type: 'connected', channel: 'tenant:t1' })).toBeNull()
    expect(parseDriverLocationEvent({ type: 'pong' })).toBeNull()
    expect(
      parseDriverLocationEvent({ type: 'event', event: { type: 'delivery.assigned', data: {} } })
    ).toBeNull()
  })

  it('rejeita coordenadas inválidas ou driver ausente', () => {
    expect(parseDriverLocationEvent(event({ latitude: 'x', longitude: -46.63 }))).toBeNull()
    expect(parseDriverLocationEvent(event({ driver_id: '', latitude: 1, longitude: 1 }))).toBeNull()
    expect(parseDriverLocationEvent(null)).toBeNull()
  })
})

// Relógio fixo: os pontos usam '2026-09-22T12:00:00Z', então o "agora" dos
// testes precisa ser explícito (senão a janela deslizante os descarta).
const NOW = Date.parse('2026-09-22T12:00:00Z')

describe('appendPoint / mergeTrackingState', () => {
  it('acumula e ordena por recorded_at', () => {
    let trail: DriverLocationUpdate[] = []
    trail = appendPoint(trail, point({ recorded_at: '2026-09-22T12:00:20Z' }), { now: NOW })
    trail = appendPoint(trail, point({ recorded_at: '2026-09-22T12:00:00Z', latitude: -23.5 }), { now: NOW })

    expect(trail.map((p) => p.recorded_at)).toEqual([
      '2026-09-22T12:00:00Z',
      '2026-09-22T12:00:20Z',
    ])
  })

  it('deduplica por recorded_at (replay do WS não duplica o trajeto)', () => {
    let trail: DriverLocationUpdate[] = []
    trail = appendPoint(trail, point({ recorded_at: '2026-09-22T12:00:00Z' }), { now: NOW })
    const again = appendPoint(trail, point({ recorded_at: '2026-09-22T12:00:00Z', latitude: -99 }), {
      now: NOW,
    })
    expect(again).toHaveLength(1)
    expect(again[0]!.latitude).toBe(-23.55)
  })

  it('aplica o teto de pontos mantendo os mais recentes', () => {
    const base = Date.parse('2026-09-22T12:00:00Z')
    let trail: DriverLocationUpdate[] = []
    for (let i = 0; i < 10; i++) {
      trail = appendPoint(
        trail,
        point({ recorded_at: new Date(base + i * 1000).toISOString(), latitude: -23.5 - i * 0.001 }),
        { maxPoints: 3, now: base + 60_000 }
      )
    }
    expect(trail).toHaveLength(3)
    expect(trail[2]!.latitude).toBeCloseTo(-23.509)
  })

  it('descarta pontos fora da janela de tempo', () => {
    const base = Date.parse('2026-09-22T12:00:00Z')
    const trail = appendPoint([], point({ recorded_at: '2026-09-22T10:00:00Z' }), {
      windowMs: 30 * 60 * 1000,
      now: base,
    })
    expect(trail).toHaveLength(0)
  })

  it('mergeTrackingState mantém o trajeto por driver', () => {
    let state = mergeTrackingState({}, point({ driver_id: 'a' }), { now: NOW })
    state = mergeTrackingState(state, point({ driver_id: 'b' }), { now: NOW })
    state = mergeTrackingState(state, point({ driver_id: 'a', recorded_at: '2026-09-22T12:00:10Z' }), {
      now: NOW,
    })

    expect(state.a!).toHaveLength(2)
    expect(state.b!).toHaveLength(1)
  })
})

describe('parseDriverAlertEvent (Fase 7.3)', () => {
  it('extrai STALLED com minutos', () => {
    const alert = parseDriverAlertEvent({
      type: 'event',
      event: {
        type: 'driver.alert',
        aggregate_id: 'drv7',
        data: { kind: 'STALLED', driver_id: 'drv7', delivery_id: 'd1', minutes: 10, moved_m: 12.5 },
      },
    })
    expect(alert).toMatchObject({ kind: 'STALLED', driver_id: 'drv7', delivery_id: 'd1', minutes: 10 })
  })

  it('extrai DEVIATED com o desvio em km', () => {
    const alert = parseDriverAlertEvent({
      type: 'event',
      event: {
        type: 'driver.alert',
        aggregate_id: 'drv7',
        data: { kind: 'DEVIATED', deviation_km: 2.4 },
      },
    })
    expect(alert).toMatchObject({ kind: 'DEVIATED', driver_id: 'drv7', deviation_km: 2.4 })
  })

  it('ignora eventos de posição e mensagens de controle', () => {
    expect(parseDriverAlertEvent(event({ latitude: 1, longitude: 1 }))).toBeNull()
    expect(parseDriverAlertEvent({ type: 'pong' })).toBeNull()
  })

  it('rejeita kind desconhecido', () => {
    const alert = parseDriverAlertEvent({
      type: 'event',
      event: { type: 'driver.alert', data: { kind: 'OUTRO', driver_id: 'drv1' } },
    })
    expect(alert).toBeNull()
  })
})

describe('latestByDriver', () => {
  it('devolve o ponto mais recente de cada trajeto', () => {
    let state = mergeTrackingState({}, point({ recorded_at: '2026-09-22T12:00:00Z', latitude: -23.55 }), {
      now: NOW,
    })
    state = mergeTrackingState(
      state,
      point({ recorded_at: '2026-09-22T12:00:30Z', latitude: -23.56 }),
      { now: NOW }
    )

    const last = latestByDriver(state)
    expect(last.drv1!.latitude).toBeCloseTo(-23.56)
  })

  it('ignora trajetos vazios', () => {
    expect(latestByDriver({ drv1: [] })).toEqual({})
  })
})
