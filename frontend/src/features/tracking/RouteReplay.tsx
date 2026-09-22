/**
 * RouteReplay — replay do dia do entregador (Fase 7.4).
 *
 * Zero backend novo: `GET /driver/locations/history` já devolve os pontos
 * ordenados. O `DriverMap` já desenha a polyline via `trails` (Fase 6), então o
 * replay é só avançar o cursor sobre o histórico.
 */
import { useEffect, useMemo, useState } from 'react'
import { Loader2, Play, Pause, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { DriverMap } from '@/components/map/DriverMap'
import { useDriverHistory } from '@/lib/api/hooks'

const TICK_MS = 250
/** Quantos pontos avançam por tick (histórico do dia pode ter milhares). */
const STEP = 5

interface RouteReplayProps {
  driverId: string
  /** Início do dia (ISO). Default: hoje no fuso local do navegador. */
  day?: string
  className?: string
}

function startOfLocalDay(iso?: string): string {
  const base = iso ? new Date(iso) : new Date()
  base.setHours(0, 0, 0, 0)
  return base.toISOString()
}

export function RouteReplay({ driverId, day, className = 'h-96' }: RouteReplayProps) {
  const { data, isLoading } = useDriverHistory(driverId, { fromTs: startOfLocalDay(day) })
  const points = useMemo(() => data?.points ?? [], [data])
  const [cursor, setCursor] = useState(0)
  const [playing, setPlaying] = useState(true)

  useEffect(() => {
    setCursor(points.length ? 1 : 0)
  }, [points.length])

  useEffect(() => {
    if (!playing || points.length < 2) return
    const timer = setInterval(() => {
      setCursor((c) => (c + STEP >= points.length ? 1 : c + STEP))
    }, TICK_MS)
    return () => clearInterval(timer)
  }, [playing, points.length])

  if (isLoading) {
    return (
      <div className={`${className} flex items-center justify-center`}>
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (points.length < 2) {
    return (
      <div
        className={`${className} flex items-center justify-center rounded-lg border border-border bg-muted/30 text-sm text-muted-foreground`}
      >
        Sem trajeto registrado hoje para este entregador.
      </div>
    )
  }

  const visible = points.slice(0, Math.max(1, cursor))
  // O DriverMap espera pontos no formato do mapa; o último visível é o marcador.
  const last = visible[visible.length - 1]
  const marker = last
    ? [
        {
          driver_id: driverId,
          latitude: last.latitude,
          longitude: last.longitude,
          timestamp: last.recorded_at,
          is_stale: false,
        },
      ]
    : []

  return (
    <div className="space-y-2">
      <DriverMap
        points={marker}
        trails={{
          [driverId]: visible.map((p) => ({
            driver_id: driverId,
            latitude: p.latitude,
            longitude: p.longitude,
            recorded_at: p.recorded_at,
          })),
        }}
        className={className}
      />
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setPlaying((p) => !p)}>
          {playing ? <Pause className="mr-1 h-3 w-3" /> : <Play className="mr-1 h-3 w-3" />}
          {playing ? 'Pausar' : 'Reproduzir'}
        </Button>
        <Button variant="outline" size="sm" onClick={() => setCursor(1)}>
          <RotateCcw className="mr-1 h-3 w-3" />
          Reiniciar
        </Button>
        <span className="text-xs text-muted-foreground">
          {visible.length}/{points.length} pontos
        </span>
      </div>
    </div>
  )
}
