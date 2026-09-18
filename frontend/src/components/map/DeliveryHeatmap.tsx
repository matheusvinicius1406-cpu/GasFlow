import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Flame } from 'lucide-react'

/**
 * DeliveryHeatmap — densidade de entregas por bairro (F8).
 *
 * Leaflet + tiles OSM (mesma base do DriverMap, sem dependência nova).
 * Cada bairro com centroide vira um círculo: raio e cor escalam com a
 * contagem (verde → amarelo → vermelho). Popup com o número. Sem postgis,
 * sem API key; só visualização (E3 — nada de posicionamento aqui).
 *
 * Bairros sem centroide (entregas sem lat/lng) NÃO vão para o mapa —
 * seguem visíveis na lista lateral da página.
 */

export interface HeatCell {
  neighborhood: string
  count: number
  center: { lat: number; lng: number } | null
}

interface DeliveryHeatmapProps {
  cells: HeatCell[]
  /** Altura do mapa (classe Tailwind no container). Default: h-96. */
  className?: string
}

/** Verde (pouco) → amarelo (médio) → vermelho (denso). */
function colorFor(ratio: number): string {
  if (ratio < 0.34) return '#16a34a'
  if (ratio < 0.67) return '#eab308'
  return '#dc2626'
}

/** Raio em metros: 150m (1 entrega) até 900m (densidade máxima). */
function radiusFor(count: number, maxCount: number): number {
  if (maxCount <= 1) return 300
  return 150 + 750 * (count / maxCount)
}

export function DeliveryHeatmap({ cells, className = 'h-96' }: DeliveryHeatmapProps) {
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

  // Re-renderiza a camada quando as células mudam.
  useEffect(() => {
    const map = mapRef.current
    const layer = layerRef.current
    if (!map || !layer) return

    layer.clearLayers()
    const mappable = cells.filter((c) => c.center && Number.isFinite(c.center.lat) && Number.isFinite(c.center.lng))
    const maxCount = Math.max(1, ...mappable.map((c) => c.count))

    for (const cell of mappable) {
      const ratio = cell.count / maxCount
      const color = colorFor(ratio)
      L.circle([cell.center!.lat, cell.center!.lng], {
        radius: radiusFor(cell.count, maxCount),
        color,
        weight: 1,
        fillColor: color,
        fillOpacity: 0.45,
      })
        .bindPopup(
          `<strong>${escapeHtml(cell.neighborhood)}</strong><br/>${cell.count} entrega${cell.count !== 1 ? 's' : ''} no período`
        )
        .addTo(layer)
    }

    if (mappable.length > 0) {
      const bounds = L.latLngBounds(mappable.map((c) => [c.center!.lat, c.center!.lng] as [number, number]))
      map.fitBounds(bounds.pad(0.25), { maxZoom: 15 })
    }
  }, [cells])

  const mappable = cells.filter((c) => c.center)
  if (cells.length === 0) {
    return (
      <div className={`${className} flex items-center justify-center rounded-lg border border-border bg-muted/30`}>
        <div className="text-center text-muted-foreground">
          <Flame className="mx-auto mb-2 h-6 w-6 opacity-50" />
          <p className="text-sm">Sem entregas no período.</p>
          <p className="text-xs">O mapa mostra a densidade quando houver entregas concluídas.</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div ref={containerRef} className={`${className} z-0 rounded-lg border border-border`} aria-label="Mapa de calor de entregas por bairro" />
      <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
        <span>Menos</span>
        <span className="inline-block h-3 w-6 rounded" style={{ background: colorFor(0) }} />
        <span className="inline-block h-3 w-6 rounded" style={{ background: colorFor(0.5) }} />
        <span className="inline-block h-3 w-6 rounded" style={{ background: colorFor(1) }} />
        <span>Mais</span>
        {mappable.length < cells.length && (
          <span className="ml-auto">
            {cells.length - mappable.length} bairro(s) sem coordenadas ficam fora do mapa.
          </span>
        )}
      </div>
    </div>
  )
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] ?? c)
}
