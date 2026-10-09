import { useCallback, useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line,
} from 'recharts'
import { FileDown, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { apiClient } from '@/lib/api/client'
import { exportCurrentViewPdf } from '@/lib/exportPdf'
import { axisTick, countYAxisProps, dateXAxisProps, gridProps, ChartFrame, CHART_MARGIN } from '../chartKit'
import { chartVar, useChartThemeTick } from '../chartTokens'

interface DayPoint { day: string; created: number; delivered: number; failed: number }
interface DriverPoint { driver_id: string; assigned: number; delivered: number; failed: number; avg_minutes: number | null }
interface NeighborhoodPoint { neighborhood: string; count: number }

interface DeliveryReport {
  days: number
  generated_at: string
  by_day: DayPoint[]
  by_driver: DriverPoint[]
  by_neighborhood: NeighborhoodPoint[]
}

const PERIODS = [7, 30, 90] as const

/** Exporta a seção de gráficos como PDF (bridge Electron com fallback para o
 * diálogo de impressão — ver `lib/exportPdf`). */
function useExportPdf() {
  const [exporting, setExporting] = useState(false)

  const exportPdf = useCallback(async () => {
    setExporting(true)
    try {
      await exportCurrentViewPdf()
    } finally {
      setExporting(false)
    }
  }, [])

  return { exportPdf, exporting }
}

/**
 * Gráficos de entregas (movido de `features/reports` no P8 / V5): buscador
 * próprio com recorte 7/30/90 e exportação em PDF. Renderizado dentro da
 * seção Equipe.
 */
export function DeliveryCharts() {
  const [days, setDays] = useState<number>(30)
  const [data, setData] = useState<DeliveryReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const { exportPdf, exporting } = useExportPdf()
  // Dispara re-render na troca de tema para as cores (chartVar) re-resolverem.
  useChartThemeTick()

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const res = await apiClient.get('/reports/deliveries', { params: { days } })
      setData(res.data)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [days])

  // Busca inicial apenas (F2 do bloco 6: refresh manual, sem auto-refresh)
  useEffect(() => {
    fetchData()
  }, [fetchData])

  return (
    <div className="space-y-4" data-testid="delivery-charts">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1" role="group" aria-label="Período dos gráficos">
          {PERIODS.map((p) => (
            <Button key={p} size="sm" variant={days === p ? 'default' : 'outline'} onClick={() => setDays(p)}>
              {p} dias
            </Button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={fetchData} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Atualizar
          </Button>
          <Button size="sm" variant="outline" onClick={exportPdf} disabled={exporting}>
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}
            Exportar PDF
          </Button>
        </div>
      </div>

      {loading && !data ? (
        <div className="flex items-center justify-center py-12">
          <LoadingSpinner size="lg" />
        </div>
      ) : error ? (
        <EmptyState
          icon={FileDown}
          title="Não foi possível carregar os gráficos"
          description="Verifique a conexão com o backend e tente novamente."
          action={<Button onClick={fetchData}>Tentar novamente</Button>}
        />
      ) : data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Entregas por período */}
          <Card className="avoid-break lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Entregas por dia</CardTitle>
            </CardHeader>
            <CardContent>
              {data.by_day.length === 0 ? (
                <EmptyState icon={FileDown} title="Sem dados" description="Nenhuma entrega na janela." />
              ) : (
                <ChartFrame
                  height={260}
                  label={`Entregas por dia nos últimos ${days} dias — criadas, entregues e falhas`}
                >
                  <LineChart data={data.by_day} margin={CHART_MARGIN}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="day" {...dateXAxisProps} />
                    <YAxis {...countYAxisProps} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="created" name="Criadas" stroke={chartVar('--muted-foreground')} strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="delivered" name="Entregues" stroke={chartVar('--success')} strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="failed" name="Falhas" stroke={chartVar('--destructive')} strokeWidth={2} dot={false} />
                  </LineChart>
                </ChartFrame>
              )}
            </CardContent>
          </Card>

          {/* Performance por entregador */}
          <Card className="avoid-break">
            <CardHeader>
              <CardTitle className="text-base">Comparativo por entregador</CardTitle>
            </CardHeader>
            <CardContent>
              {data.by_driver.length === 0 ? (
                <EmptyState icon={FileDown} title="Sem dados" description="Nenhuma entrega atribuída." />
              ) : (
                <ChartFrame height={240} label="Entregas e falhas por entregador">
                  <BarChart data={data.by_driver} margin={CHART_MARGIN}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="driver_id" tick={{ fontSize: 10 }} />
                    <YAxis {...countYAxisProps} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="delivered" name="Entregues" fill={chartVar('--success')} radius={[3, 3, 0, 0]} />
                    <Bar dataKey="failed" name="Falhas" fill={chartVar('--destructive')} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ChartFrame>
              )}
            </CardContent>
          </Card>

          {/* Tempo médio de entrega (atribuição → DELIVERED) */}
          <Card className="avoid-break">
            <CardHeader>
              <CardTitle className="text-base">Tempo médio de entrega (min)</CardTitle>
            </CardHeader>
            <CardContent>
              {data.by_driver.filter((d) => d.avg_minutes != null).length === 0 ? (
                <EmptyState icon={FileDown} title="Sem dados" description="Nenhuma entrega concluída com tempo medido." />
              ) : (
                <ChartFrame
                  height={240}
                  label="Tempo médio de entrega por entregador, em minutos (atribuição → entrega)"
                >
                  <BarChart data={data.by_driver.filter((d) => d.avg_minutes != null)} margin={CHART_MARGIN}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="driver_id" tick={{ fontSize: 10 }} />
                    <YAxis width={48} tick={axisTick} tickFormatter={(value) => `${Number(value)} min`} />
                    <Tooltip formatter={(value) => `${Number(value)} min`} />
                    <Bar dataKey="avg_minutes" name="Minutos (atribuição → entrega)" fill={chartVar('--info')} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ChartFrame>
              )}
            </CardContent>
          </Card>

          {/* Por região (bairro) */}
          <Card className="avoid-break lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Entregas por bairro</CardTitle>
            </CardHeader>
            <CardContent>
              {data.by_neighborhood.length === 0 ? (
                <EmptyState icon={FileDown} title="Sem dados" description="Nenhuma entrega concluída." />
              ) : (
                <ChartFrame height={240} label="Entregas concluídas por bairro">
                  <BarChart data={data.by_neighborhood} margin={CHART_MARGIN}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="neighborhood" tick={{ fontSize: 10 }} interval={0} angle={-20} height={50} textAnchor="end" />
                    <YAxis {...countYAxisProps} />
                    <Tooltip />
                    <Bar dataKey="count" name="Entregas" fill={chartVar('--warning')} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ChartFrame>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  )
}
