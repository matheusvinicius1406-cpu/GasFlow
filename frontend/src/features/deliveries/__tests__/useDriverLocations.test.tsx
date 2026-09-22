/**
 * useDriverLocations — F1b: polling de 30s das posições dos entregadores.
 *
 * Testa o contrato do hook contra a resposta real do GET /delivery/locations
 * ({ locations: [...] }): primeira carga + refetch automático no intervalo.
 * apiClient é mockado — o que importa aqui é o comportamento do React Query
 * (carga inicial, extração de `locations` e polling), não o transport HTTP.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useDriverLocations } from '@/lib/api/hooks'
import { api } from '@/lib/api/client'

const locationsPayload = {
  locations: [
    {
      driver_id: 'driver1',
      latitude: -30.0346,
      longitude: -51.2177,
      accuracy: 10,
      speed: 2.5,
      bearing: 90,
      timestamp: new Date().toISOString(),
      is_stale: false,
      age_seconds: 5,
    },
  ],
}

const getMock = vi.fn()

vi.mock('@/lib/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/client')>()
  return {
    ...actual,
    apiClient: { get: (...args: unknown[]) => getMock(...args) },
    api: { deliveryOps: { ...(actual as { api: { deliveryOps: object } }).api.deliveryOps } },
  }
})

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useDriverLocations (F1b)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getMock.mockResolvedValue({ data: locationsPayload })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('carrega as posições do endpoint /delivery/locations', async () => {
    const { result } = renderHook(() => useDriverLocations(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(getMock).toHaveBeenCalledWith('/delivery/locations')
    expect(result.current.data).toHaveLength(1)
    expect(result.current.data?.[0]).toMatchObject({
      driver_id: 'driver1',
      latitude: -30.0346,
      longitude: -51.2177,
      is_stale: false,
    })
  })

  it('F6: não faz polling automático (posições vêm por WebSocket)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { result } = renderHook(() => useDriverLocations(), { wrapper: createWrapper() })

    // Primeira carga completa (timers avançam automaticamente — shouldAdvanceTime)
    await waitFor(() => expect(result.current.data).toHaveLength(1), { timeout: 3000 })
    const callsAfterFirstLoad = getMock.mock.calls.length
    expect(callsAfterFirstLoad).toBeGreaterThan(0)

    // Avança 31s → SEM refetch (o polling de 30s foi substituído por
    // useTrackingSocket; este hook é só a carga inicial/fallback).
    await vi.advanceTimersByTimeAsync(31_000)

    expect(getMock.mock.calls.length).toBe(callsAfterFirstLoad)
  })

  it('retorna lista vazia quando o backend não tem posições', async () => {
    getMock.mockResolvedValue({ data: { locations: [] } })
    const { result } = renderHook(() => useDriverLocations(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })

  it('referencia api.deliveryOps sem quebrar o mock do módulo (importOriginal)', () => {
    // Garante que o spread do módulo original preservou os outros hooks.
    expect(typeof api.deliveryOps.dispatchSummary).toBe('function')
  })
})
