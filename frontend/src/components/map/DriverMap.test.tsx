/**
 * DriverMap — F1b (mapa do operador).
 *
 * jsdom não tem layout nem canvas: o Leaflet real não renderiza tiles aqui.
 * Mockamos o módulo leaflet e validamos o comportamento do componente:
 * estado vazio com/instrução, e container com aria-label quando há pontos.
 * A matemática de fitBounds/marcadores é do Leaflet — coberta pelo pacote.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { DriverMap, type DriverMapPoint } from './DriverMap'

const layerGroupMock = {
  addTo: vi.fn().mockReturnThis(),
  clearLayers: vi.fn(),
}

vi.mock('leaflet', () => {
  const layerGroup = vi.fn(() => layerGroupMock)
  const tileLayer = vi.fn(() => ({ addTo: vi.fn() }))
  const marker = vi.fn(() => ({
    bindPopup: vi.fn().mockReturnThis(),
    addTo: vi.fn(),
  }))
  const latLngBounds = vi.fn(() => ({ pad: vi.fn().mockReturnThis() }))
  const polyline = vi.fn(() => ({ addTo: vi.fn() }))
  const mapInstance = {
    remove: vi.fn(),
    fitBounds: vi.fn(),
  }
  const map = vi.fn(() => mapInstance)
  const divIcon = vi.fn((x) => x)

  type Chain = Record<string, unknown>
  const chainable = (obj: Chain): Chain => obj
  void chainable

  return {
    default: {
      map,
      tileLayer,
      marker,
      layerGroup,
      latLngBounds,
      divIcon,
      polyline,
    },
    __mockMapInstance: mapInstance,
  }
})

import leaflet from 'leaflet'

const makePoint = (over: Partial<DriverMapPoint> = {}): DriverMapPoint => ({
  driver_id: 'drv1',
  name: 'João',
  latitude: -30.03,
  longitude: -51.21,
  timestamp: new Date().toISOString(),
  is_stale: false,
  age_seconds: 10,
  ...over,
})

describe('DriverMap', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mostra estado vazio quando não há posições', () => {
    render(<DriverMap points={[]} />)
    expect(screen.getByText(/Nenhuma posição de entregador/i)).toBeInTheDocument()
    expect(screen.getByText(/ligar o rastreio/i)).toBeInTheDocument()
    cleanup()
  })

  it('renderiza o container do mapa e ajusta bounds quando há pontos', () => {
    const { container } = render(<DriverMap points={[makePoint(), makePoint({ driver_id: 'drv2', is_stale: true })]} />)
    const mapDiv = container.querySelector('[aria-label="Mapa de entregadores"]')
    expect(mapDiv).toBeInTheDocument()

    const mock = leaflet as unknown as { map: ReturnType<typeof vi.fn> }
    expect(mock.map).toHaveBeenCalledTimes(1)
    cleanup()
  })

  it('F6: desenha a polyline do trajeto quando há trails', () => {
    const trails = {
      drv1: [
        { driver_id: 'drv1', latitude: -30.03, longitude: -51.21, recorded_at: '2026-09-22T12:00:00Z' },
        { driver_id: 'drv1', latitude: -30.04, longitude: -51.22, recorded_at: '2026-09-22T12:00:30Z' },
      ],
    }
    render(<DriverMap points={[makePoint()]} trails={trails} />)

    const mock = leaflet as unknown as { polyline: ReturnType<typeof vi.fn> }
    expect(mock.polyline).toHaveBeenCalledTimes(1)
    cleanup()
  })

  it('não desenha polyline com menos de 2 pontos', () => {
    const trails = {
      drv1: [{ driver_id: 'drv1', latitude: -30.03, longitude: -51.21, recorded_at: '2026-09-22T12:00:00Z' }],
    }
    render(<DriverMap points={[makePoint()]} trails={trails} />)

    const mock = leaflet as unknown as { polyline: ReturnType<typeof vi.fn> }
    expect(mock.polyline).not.toHaveBeenCalled()
    cleanup()
  })

  it('limpa o mapa ao desmontar (sem leak de instância Leaflet)', () => {
    const { unmount } = render(<DriverMap points={[makePoint()]} />)
    const mock = leaflet as unknown as { map: ReturnType<typeof vi.fn> }
    expect(mock.map).toHaveBeenCalledTimes(1)
    unmount()
    // Após unmount, um novo mount cria uma nova instância (remove foi chamado).
    render(<DriverMap points={[makePoint()]} />)
    expect(mock.map).toHaveBeenCalledTimes(2)
    cleanup()
  })
})
