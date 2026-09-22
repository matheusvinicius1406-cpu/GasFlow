/**
 * DriverMap — F1b + Fase 6 + Parte 1 (fixes 5 e 6).
 *
 * jsdom não tem layout nem canvas: o Leaflet real não renderiza tiles aqui.
 * Mockamos o módulo leaflet e validamos o comportamento do componente:
 * estado vazio, container, trails, e — o que os fixes 5/6 cobrem — **de onde
 * parte a linha do destino** e **como o ETA é rotulado**.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { DriverMap, type DriverMapPoint } from './DriverMap'

// `vi.hoisted` é obrigatório aqui: `vi.mock` é içado acima dos imports, então
// qualquer const declarada depois cairia em TDZ na hora de montar a factory.
const mocks = vi.hoisted(() => ({
  layerGroup: { addTo: vi.fn().mockReturnThis(), clearLayers: vi.fn() },
  // Capturado para inspecionarmos o HTML do popup do destino.
  bindPopup: vi.fn(() => ({ addTo: vi.fn() })),
}))

vi.mock('leaflet', () => {
  const layerGroup = vi.fn(() => mocks.layerGroup)
  const tileLayer = vi.fn(() => ({ addTo: vi.fn() }))
  const marker = vi.fn(() => ({
    bindPopup: mocks.bindPopup,
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
    __bindPopup: mocks.bindPopup,
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

/** Última polyline tracejada (a do destino) e o primeiro ponto dela. */
function dashedOrigin(): [number, number] {
  const mock = leaflet as unknown as { polyline: ReturnType<typeof vi.fn> }
  const dashed = mock.polyline.mock.calls.filter(
    (call) => (call[1] as { dashArray?: string } | undefined)?.dashArray
  )
  expect(dashed.length).toBeGreaterThan(0)
  const path = dashed[dashed.length - 1]![0] as [number, number][]
  return path[0]!
}

/** HTML do popup do destino. */
function destinationPopup(): string {
  const calls = mocks.bindPopup.mock.calls as unknown as [string][]
  const html = calls.map((c) => String(c[0]))
  return html.find((h) => h.includes('Destino')) ?? ''
}

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

  // ── Parte 1, fix 5/6 ────────────────────────────────────

  it('fix 6: a linha do destino NÃO parte da primeira posição da lista', () => {
    const points = [
      makePoint({ driver_id: 'antigo', latitude: -30.01, longitude: -51.11 }),
      makePoint({ driver_id: 'atual', latitude: -30.05, longitude: -51.25 }),
    ]
    render(
      <DriverMap
        points={points}
        destination={{ latitude: -30.09, longitude: -51.30, etaLabel: '12 min' }}
      />
    )

    // Sem `driverId`, a origem é a ÚLTIMA posição — antes saía da primeira.
    expect(dashedOrigin()).toEqual([-30.05, -51.25])
    cleanup()
  })

  it('fix 5: usa a posição do entregador do destino quando informado', () => {
    const points = [
      makePoint({ driver_id: 'alheio', latitude: -30.01, longitude: -51.11 }),
      makePoint({ driver_id: 'dono', latitude: -30.05, longitude: -51.25 }),
    ]
    render(
      <DriverMap
        points={points}
        destination={{
          latitude: -30.09,
          longitude: -51.30,
          etaLabel: '12 min',
          driverId: 'alheio',
        }}
      />
    )

    expect(dashedOrigin()).toEqual([-30.01, -51.11])
    cleanup()
  })

  it('fix 5: ETA estimado ganha "~" e aviso de estimativa', () => {
    render(
      <DriverMap
        points={[makePoint()]}
        destination={{
          latitude: -30.09,
          longitude: -51.30,
          etaLabel: '12 min',
          speedSource: 'default',
        }}
      />
    )

    const html = destinationPopup()
    expect(html).toContain('~12 min')
    expect(html).toContain('estimado')
    cleanup()
  })

  it('fix 5: ETA medido sai sem "~"', () => {
    render(
      <DriverMap
        points={[makePoint()]}
        destination={{
          latitude: -30.09,
          longitude: -51.30,
          etaLabel: '8 min',
          speedSource: 'history',
        }}
      />
    )

    const html = destinationPopup()
    expect(html).toContain('Chega em 8 min')
    expect(html).not.toContain('~')
    cleanup()
  })
})
