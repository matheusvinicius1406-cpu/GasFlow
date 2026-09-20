import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend,
} from 'recharts'
import { FileDown, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { apiClient } from '@/lib/api/client'
import { exportCurrentViewPdf } from '@/lib/exportPdf'

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
  const sectionRef = useRef<HTMLDivElement | null>(null)

  const exportPdf = useCallback(async () => {
    setExporting(true)
    try {
      await exportCurrentViewPdf()
    } finally {
      setExporting(false)
    }
  }, [])

  return { exportPdf, exporting, sectionRef }
}

export function DeliveryCharts() {
  const [days, setDays] = useState<number>(30)
  const [data, setData] = useState<DeliveryReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const { exportPdf, exporting, sectionRef } = useExportPdf()

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
        <div ref={sectionRef} className="grid gap-4 lg:grid-cols-2">
          {/* Entregas por período */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Entregas por dia</CardTitle>
            </CardHeader>
            <CardContent>
              {data.by_day.length === 0 ? (
                <EmptyState icon={FileDown} title="Sem dados" description="Nenhuma entrega na janela." />
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={data.by_day} margin={{ top: 5, right: 12, left: -18, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="day" tick={{ fontSize: 11 }} tickFormatter={(d: string) => d.slice(5)} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="created" name="Criadas" stroke="#64748b" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="delivered" name="Entregues" stroke="#16a34a" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="failed" name="Falhas" stroke="#dc2626" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Performance por entregador */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Comparativo por entregador</CardTitle>
            </CardHeader>
            <CardContent>
              {data.by_driver.length === 0 ? (
                <EmptyState icon={FileDown} title="Sem dados" description="Nenhuma entrega atribuída." />
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={data.by_driver} margin={{ top: 5, right: 12, left: -18, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="driver_id" tick={{ fontSize: 10 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="delivered" name="Entregues" fill="#16a34a" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="failed" name="Falhas" fill="#dc2626" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Tempo médio de entrega (atribuição → DELIVERED) */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Tempo médio de entrega (min)</CardTitle>
            </CardHeader>
            <CardContent>
              {data.by_driver.filter((d) => d.avg_minutes != null).length === 0 ? (
                <EmptyState icon={FileDown} title="Sem dados" description="Nenhuma entrega concluída com tempo medido." />
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={data.by_driver.filter((d) => d.avg_minutes != null)} margin={{ top: 5, right: 12, left: -18, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="driver_id" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="avg_minutes" name="Minutos (atribuição → entrega)" fill="#2563eb" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Por região (bairro) */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Entregas por bairro</CardTitle>
            </CardHeader>
            <CardContent>
              {data.by_neighborhood.length === 0 ? (
                <EmptyState icon={FileDown} title="Sem dados" description="Nenhuma entrega concluída." />
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={data.by_neighborhood} margin={{ top: 5, right: 12, left: -18, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="neighborhood" tick={{ fontSize: 10 }} interval={0} angle={-20} height={50} textAnchor="end" />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" name="Entregas" fill="#eab308" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  )
}
