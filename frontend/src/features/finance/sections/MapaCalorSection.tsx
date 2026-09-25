import { useCallback, useEffect, useState } from 'react'
import { Flame, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { DeliveryHeatmap, type HeatCell } from '@/components/map/DeliveryHeatmap'
import { apiClient } from '@/lib/api/client'

interface HeatmapResponse {
  period_days: number
  generated_at: string
  cached: boolean
  total: number
  neighborhoods: HeatCell[]
}

const PERIODS = [7, 30, 90] as const

/**
 * Mapa de Calor (movido de `HeatmapPage` no P8 / D4) — densidade de entregas
 * concluídas por bairro. Mantém o recorte próprio (7/30/90) porque o
 * endpoint `/reports/heatmap` só aceita esses dias; a API não mudou.
 */
export function MapaCalorSection() {
  const [days, setDays] = useState<number>(30)
  const [data, setData] = useState<HeatmapResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const res = await apiClient.get('/reports/heatmap', { params: { days } })
      setData(res.data)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const maxCount = Math.max(1, ...(data?.neighborhoods ?? []).map((n) => n.count))

  return (
    <div className="space-y-4" data-testid="mapa-calor-section">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1" role="group" aria-label="Período do mapa de calor">
          {PERIODS.map((p) => (
            <Button
              key={p}
              size="sm"
              variant={days === p ? 'default' : 'outline'}
              aria-pressed={days === p}
              onClick={() => setDays(p)}
            >
              {p} dias
            </Button>
          ))}
        </div>
        <Button variant="outline" onClick={fetchData}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <LoadingSpinner size="lg" />
        </div>
      ) : error ? (
        <ErrorState message="Não foi possível carregar o mapa de calor." onRetry={fetchData} />
      ) : data ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Flame className="h-4 w-4 text-warning" />
                Densidade por bairro — {data.total} entrega(s) em {data.period_days} dias
                {data.cached && <span className="text-xs font-normal text-muted-foreground">(cache 5min)</span>}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <DeliveryHeatmap cells={data.neighborhoods} />
            </CardContent>
          </Card>

          {data.neighborhoods.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Ranking de bairros</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {data.neighborhoods.map((n) => (
                    <div key={n.neighborhood} className="flex items-center gap-3">
                      <span className="w-40 truncate text-sm font-medium">{n.neighborhood}</span>
                      <div className="h-3 flex-1 rounded-full bg-muted">
                        <div
                          className="h-3 rounded-full bg-primary"
                          style={{ width: `${(n.count / maxCount) * 100}%` }}
                          aria-hidden
                        />
                      </div>
                      <span className="w-12 text-right text-sm text-muted-foreground">{n.count}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      ) : null}
    </div>
  )
}
