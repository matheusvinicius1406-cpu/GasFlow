import { DollarSign, PackageCheck, PackageX } from 'lucide-react'
import { Alert } from '@/components/ui/Alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { formatCurrency, formatNumber } from '@/lib/utils'
import type { TeamData } from '../useAnalyticsData'
import { money } from '../useVisaoGeralData'
import { DeliveryCharts } from './DeliveryCharts'
import { KpiCard } from './KpiCard'

/**
 * Equipe (P8) — entregas por motorista e a folha SALARY do período, mais os
 * gráficos de entregas (`DeliveryCharts`, movido de Relatórios / V5). Sem
 * rateio de custo exato por entregador — o rótulo vem da API.
 */
export function EquipeSection({ data }: { data: TeamData }) {
  const entregues = data.by_driver.reduce((s, d) => s + d.delivered, 0)
  const falhas = data.by_driver.reduce((s, d) => s + d.failed, 0)

  return (
    <div className="space-y-6" data-testid="equipe-section">
      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard testId="equipe-entregues" title="Entregas no período" value={entregues} icon={PackageCheck} />
        <KpiCard
          testId="equipe-falhas"
          title="Falhas"
          value={falhas}
          icon={PackageX}
          emphasis={falhas > 0 ? 'negative' : undefined}
        />
        <KpiCard
          testId="equipe-folha"
          title="Folha (SALARY)"
          value={formatCurrency(money(data.salary_total))}
          icon={DollarSign}
        />
      </div>

      <Alert variant="info" title="Como ler a folha">
        {data.note || 'A folha soma apenas despesas da categoria SALARY no período — não há rateio por entregador.'}
      </Alert>

      <Card data-testid="equipe-tabela">
        <CardHeader>
          <CardTitle className="text-base">Desempenho por motorista</CardTitle>
        </CardHeader>
        <CardContent>
          {data.by_driver.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nenhuma entrega atribuída no período.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Motorista</TableHead>
                    <TableHead className="text-right">Atribuídas</TableHead>
                    <TableHead className="text-right">Entregues</TableHead>
                    <TableHead className="text-right">Falhas</TableHead>
                    <TableHead className="text-right">Tempo médio</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.by_driver.map((driver) => (
                    <TableRow key={driver.driver_id}>
                      <TableCell>
                        <div className="font-medium">{driver.nome ?? driver.driver_id}</div>
                        {driver.nome && (
                          <div className="font-mono text-xs text-muted-foreground">
                            {driver.driver_id}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="text-right">{formatNumber(driver.assigned)}</TableCell>
                      <TableCell className="text-right text-success">
                        {formatNumber(driver.delivered)}
                      </TableCell>
                      <TableCell className="text-right text-destructive">
                        {formatNumber(driver.failed)}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {driver.avg_minutes === null ? '—' : `${Math.round(driver.avg_minutes)} min`}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="space-y-3">
        <h3 className="text-base font-semibold text-foreground">Gráficos de entregas</h3>
        <DeliveryCharts />
      </div>
    </div>
  )
}
