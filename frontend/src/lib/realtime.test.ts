import { describe, it, expect, afterEach } from 'vitest'
import { realtimeQueryKeys, isRelevantEvent, buildRealtimeUrl } from './realtime'

describe('realtimeQueryKeys', () => {
  it('maps delivery events to deliveries/summary/dashboard/orders keys', () => {
    const keys = realtimeQueryKeys('delivery.started')
    expect(keys).toContainEqual(['deliveries'])
    expect(keys).toContainEqual(['delivery-summary'])
    expect(keys).toContainEqual(['dashboard'])
    expect(keys).toContainEqual(['orders'])
  })

  it('maps driver availability changes to driver list + summary', () => {
    const keys = realtimeQueryKeys('driver.available')
    expect(keys).toContainEqual(['delivery-drivers'])
    expect(keys).toContainEqual(['delivery-summary'])
    expect(keys).not.toContainEqual(['deliveries'])
  })

  it('ignores high-frequency location updates', () => {
    expect(realtimeQueryKeys('driver.location_updated')).toEqual([])
  })

  it('maps order events to the orders list + dashboard', () => {
    const keys = realtimeQueryKeys('order.created')
    expect(keys).toContainEqual(['orders'])
    expect(keys).toContainEqual(['dashboard'])
    expect(realtimeQueryKeys('order.updated')).toContainEqual(['orders'])
  })

  it('maps payment events to orders/dashboard and the finance caches', () => {
    const keys = realtimeQueryKeys('payment.confirmed')
    expect(keys).toContainEqual(['orders'])
    expect(keys).toContainEqual(['dashboard'])
    expect(keys).toContainEqual(['finance-payments'])
    expect(keys).toContainEqual(['finance-receivables'])
    expect(keys).toContainEqual(['finance-cash'])
    expect(keys).toContainEqual(['finance-balance'])
    expect(realtimeQueryKeys('payment.pending')).toContainEqual(['finance-payments'])
  })

  it('ignores unrelated events', () => {
    expect(realtimeQueryKeys('')).toEqual([])
  })
})

describe('isRelevantEvent', () => {
  it('accepts event envelopes', () => {
    expect(
      isRelevantEvent({ type: 'event', event: { type: 'delivery.completed' } })
    ).toBe(true)
  })

  it('rejects pings, pongs and non-event messages', () => {
    expect(isRelevantEvent({ type: 'connected', channel: 'tenant:1' })).toBe(false)
    expect(isRelevantEvent({ type: 'pong' })).toBe(false)
    expect(isRelevantEvent({ type: 'event', event: undefined })).toBe(false)
  })
})

describe('buildRealtimeUrl', () => {
  afterEach(() => {
    // restore default protocol
    window.history.replaceState({}, '', '/')
  })

  it('builds ws:// URL on http origins with the token', () => {
    expect(buildRealtimeUrl('abc123')).toBe(
      `ws://${window.location.host}/ws?token=abc123`
    )
  })

  it('builds wss:// URL on https origins', () => {
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...window.location, protocol: 'https:', host: 'gasflow.app' },
    })
    expect(buildRealtimeUrl('tok')).toBe('wss://gasflow.app/ws?token=tok')
  })
})
