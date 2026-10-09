import { ArrowDownCircle, ArrowUpCircle, Info, Wallet } from 'lucide-react'
import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts'
import { Alert } from '@/components/ui/Alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { formatCurrency } from '@/lib/utils'
import { chartVar, useChartThemeTick } from '../chartTokens'
import {
  CHART_MARGIN,
  ChartFrame,
  dateXAxisProps,
  gridProps,
  moneyTooltipProps,
  moneyYAxisProps,
} from '../chartKit'
import type { ProjectionData } from '../useAnalyticsData'
import { money } from '../useVisaoGeralData'
import { KpiCard } from './KpiCard'

/**
 * Projeção de caixa (P6) — saldo atual + recebíveis no horizonte − média
 * histórica de despesas. O rótulo do modelo vem da API (`model`, sem ML):
 * a seção repete para não vender precisão que não existe.
 */
export function ProjecaoSection({ data }: { data: ProjectionData }) {
  // Dispara re-render na troca de tema para as cores (chartVar) re-resolverem.
  useChartThemeTick()
  const projetado = money(data.projected_balance)
  const atual = money(data.current_balance)

  const serie = data.daily.map((d) => ({
    date: d.date,
    saldo: money(d.balance),
  }))

  return (
    <div className="space-y-6" data-testid="projecao-section">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          testId="projecao-saldo-atual"
          title="Saldo atual"
          value={formatCurrency(atual)}
          icon={Wallet}
        />
        <KpiCard
          testId="projecao-entradas"
          title="Entradas previstas"
          value={formatCurrency(money(data.expected_in))}
          icon={ArrowUpCircle}
          emphasis="positive"
        />
        <KpiCard
          testId="projecao-saidas"
          title="Saídas previstas"
          value={formatCurrency(money(data.expected_out))}
          icon={ArrowDownCircle}
          emphasis={money(data.expected_out) > 0 ? 'negative' : undefined}
        />
        <KpiCard
          testId="projecao-saldo-projetado"
          title={`Saldo em ${data.horizon} dias`}
          value={formatCurrency(projetado)}
          icon={Wallet}
          emphasis={projetado >= 0 ? 'positive' : 'negative'}
        />
      </div>

      <Alert variant="info" title="Como a projeção é calculada">
        {data.model} Despesas futuras estimadas por média de{' '}
        {formatCurrency(money(data.avg_daily_expenses))} por dia.
      </Alert>

      <Card className="avoid-break" data-testid="projecao-serie">
        <CardHeader>
          <CardTitle className="text-base">Saldo projetado por dia</CardTitle>
        </CardHeader>
        <CardContent>
          <ChartFrame
            height={300}
            label={`Saldo projetado por dia — de ${formatCurrency(atual)} hoje para ${formatCurrency(projetado)} em ${data.horizon} dias`}
          >
            <LineChart data={serie} margin={CHART_MARGIN}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...dateXAxisProps} />
              <YAxis {...moneyYAxisProps} />
              <Tooltip {...moneyTooltipProps} />
              <Line
                type="monotone"
                dataKey="saldo"
                name="Saldo projetado"
                stroke={chartVar('--info')}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ChartFrame>
          <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
            <Info className="h-3.5 w-3.5" />
            Linha de saldo acumulado — recebíveis com vencimento e média de despesas do período.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
