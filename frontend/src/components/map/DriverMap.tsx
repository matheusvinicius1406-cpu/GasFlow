import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapPin } from 'lucide-react'
import type { DriverLocationUpdate } from '@/lib/tracking'

/**
 * DriverMap — mapa do operador com a posição dos entregadores (F1b).
 *
 * Leaflet + tiles OSM (sem API key — decisão do dono 16/09). Usado nas
 * páginas Entregas e Motoristas via prop `locations`:
 *
 * - Todos os entregadores com posição aparecem.
 * - Marcador cinza quando `is_stale` (posição antiga, >5min no backend).
 * - Popup com nome/idade da posição.
 * - Sem coordenadas em logs/telemetria (LGPD).
 *
 * A posição chega por polling no pai (React Query refetchInterval 30s);
 * este componente é puramente visual e re-renderiza os marcadores quando
 * os dados mudam.
 */

export interface DriverMapPoint {
  driver_id: string
  name?: string
  latitude: number
  longitude: number
  accuracy?: number | null
  speed?: number | null
  timestamp: string
  is_stale: boolean
  age_seconds?: number
  /** Fase 7.5: distância percorrida hoje (km), quando o backend informar. */
  today_distance_km?: number
}

export interface MapDestination {
  latitude: number
  longitude: number
  /** Rótulo do ETA (ex.: "12 min") mostrado no popup do destino. */
  etaLabel?: string
}

interface DriverMapProps {
  points: DriverMapPoint[]
  /** Altura do mapa (classe Tailwind no container). Default: h-72. */
  className?: string
  /**
   * Fase 7.1: destino (endereço da entrega em rota). Desenha a **linha
   * tracejada** do entregador até o endereço do último ponto conhecido.
   */
  destination?: MapDestination
  /**
   * Fase 6: trajetos por entregador (`driver_id` → pontos ordenados). Desenha a
   * polyline do trecho recente; atualizado incrementalmente pelo WebSocket.
   */
  trails?: Record<string, DriverLocationUpdate[]>
}

/** Marcador circular: verde (fresco) / cinza (stale). */
function createDotIcon(stale: boolean): L.DivIcon {
  const color = stale ? '#9ca3af' : '#16a34a'
  return L.divIcon({
    className: 'gasflow-driver-dot',
    html: `<span style="display:block;width:16px;height:16px;border-radius:9999px;background:${color};border:3px solid white;box-shadow:0 1px 4px rgba(0,0,0,.4);"></span>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    popupAnchor: [0, -10],
  })
}

function ageLabel(ageSeconds?: number): string {
  if (ageSeconds === undefined) return 'agora'
  if (ageSeconds < 60) return `${ageSeconds}s atrás`
  const minutes = Math.floor(ageSeconds / 60)
  if (minutes < 60) return `${minutes}min atrás`
  return `${Math.floor(minutes / 60)}h atrás`
}

export function DriverMap({ points, className = 'h-72', trails, destination }: DriverMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.LayerGroup | null>(null)

  // Cria o mapa uma única vez.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = L.map(containerRef.current, {
      center: [-30.0346, -51.2177], // Porto Alegre — região de operação
      zoom: 12,
      zoomControl: true,
      attributionControl: true,
    })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)
    layerRef.current = L.layerGroup().addTo(map)
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
      layerRef.current = null
    }
  }, [])

  // Re-renderiza marcadores quando os pontos mudam.
  useEffect(() => {
    const map = mapRef.current
    const layer = layerRef.current
    if (!map || !layer) return

    layer.clearLayers()
    const valid = points.filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude))

    for (const p of valid) {
      const label = p.name || p.driver_id
      L.marker([p.latitude, p.longitude], { icon: createDotIcon(p.is_stale) })
        .bindPopup(
          `<strong>${escapeHtml(label)}</strong><br/>${p.is_stale ? 'Posição antiga' : 'Em movimento'} · ${ageLabel(p.age_seconds)}${typeof p.today_distance_km === 'number' ? `<br/>Hoje: ${p.today_distance_km.toFixed(1)} km` : ''}`
        )
        .addTo(layer)
    }

    // Fase 6: polyline do trajeto recente (mesmo trajeto = 1 origem de dados,
    // sem re-render do mapa inteiro — só a LayerGroup é reescrita).
    for (const trail of Object.values(trails ?? {})) {
      const path = trail
        .filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude))
        .map((p) => [p.latitude, p.longitude] as [number, number])
      if (path.length < 2) continue
      L.polyline(path, { color: '#16a34a', weight: 3, opacity: 0.7 }).addTo(layer)
    }

    // Fase 7.1: linha tracejada até o endereço da entrega em rota.
    if (destination && valid.length > 0) {
      const origin = valid[0]!
      L.polyline(
        [
          [origin.latitude, origin.longitude],
          [destination.latitude, destination.longitude],
        ],
        { color: '#f59e0b', weight: 3, dashArray: '6 6' }
      ).addTo(layer)
      L.marker([destination.latitude, destination.longitude], { icon: createDotIcon(false) })
        .bindPopup(
          `<strong>Destino</strong>${destination.etaLabel ? `<br/>Chega em ~${escapeHtml(destination.etaLabel)}` : ''}`
        )
        .addTo(layer)
    }

    if (valid.length > 0) {
      const bounds = L.latLngBounds(valid.map((p) => [p.latitude, p.longitude] as [number, number]))
      map.fitBounds(bounds.pad(0.25), { maxZoom: 15 })
    }
  }, [points, trails, destination])

  if (points.length === 0) {
    return (
      <div className={`${className} flex items-center justify-center rounded-lg border border-border bg-muted/30`}>
        <div className="text-center text-muted-foreground">
          <MapPin className="mx-auto mb-2 h-6 w-6 opacity-50" />
          <p className="text-sm">Nenhuma posição de entregador ainda.</p>
          <p className="text-xs">O mapa mostra o GPS quando o entregador ligar o rastreio.</p>
        </div>
      </div>
    )
  }

  return <div ref={containerRef} className={`${className} z-0 rounded-lg border border-border`} aria-label="Mapa de entregadores" />
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] ?? c)
}
