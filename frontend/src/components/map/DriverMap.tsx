import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapPin } from 'lucide-react'

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
}

interface DriverMapProps {
  points: DriverMapPoint[]
  /** Altura do mapa (classe Tailwind no container). Default: h-72. */
  className?: string
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

export function DriverMap({ points, className = 'h-72' }: DriverMapProps) {
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
          `<strong>${escapeHtml(label)}</strong><br/>${p.is_stale ? 'Posição antiga' : 'Em movimento'} · ${ageLabel(p.age_seconds)}`
        )
        .addTo(layer)
    }

    if (valid.length > 0) {
      const bounds = L.latLngBounds(valid.map((p) => [p.latitude, p.longitude] as [number, number]))
      map.fitBounds(bounds.pad(0.25), { maxZoom: 15 })
    }
  }, [points])

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
