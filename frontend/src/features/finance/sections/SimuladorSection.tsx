import { useState } from 'react'
import { Calculator, PiggyBank, TrendingUp, Wallet } from 'lucide-react'
import { Alert } from '@/components/ui/Alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { formatCurrency, formatPercent } from '@/lib/utils'
import type { SimuladorData } from '../useAnalyticsData'
import { money } from '../useVisaoGeralData'
import { KpiCard } from './KpiCard'

/**
 * Simulador what-if (P7) — "e se eu receber X% dos recebíveis em aberto e
 * reduzir as despesas em Y%?". Tudo no cliente: não altera dados.
 */
export function SimuladorSection({ data }: { data: SimuladorData }) {
  const [receberPct, setReceberPct] = useState(100)
  const [reduzirPct, setReduzirPct] = useState(0)

  const emAberto = data.receivables
    .filter((r) => money(r.remaining_amount) > 0)
    .reduce((s, r) => s + money(r.remaining_amount), 0)
  const resultadoAtual = money(data.period.net_result)
  const despesas = money(data.period.total_expenses)

  const aReceber = emAberto * (receberPct / 100)
  const economia = despesas * (reduzirPct / 100)
  const resultadoSimulado = resultadoAtual + aReceber + economia

  return (
    <div className="space-y-6" data-testid="simulador-section">
      <Card data-testid="simulador-controles">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Calculator className="h-4 w-4 text-muted-foreground" />
            Cenário
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-6 md:grid-cols-2">
          <div className="space-y-2">
            <label htmlFor="sim-receber" className="flex items-center justify-between text-sm font-medium">
              <span>Recebíveis em aberto a receber</span>
              <span className="text-muted-foreground">{formatPercent(receberPct)}</span>
            </label>
            <Input
              id="sim-receber"
              aria-label="Percentual dos recebíveis a receber"
              type="range"
              min={0}
              max={100}
              step={5}
              value={receberPct}
              onChange={(e) => setReceberPct(Number(e.target.value))}
            />
            <p className="text-xs text-muted-foreground">
              Base: {formatCurrency(emAberto)} em aberto
            </p>
          </div>

          <div className="space-y-2">
            <label htmlFor="sim-reduzir" className="flex items-center justify-between text-sm font-medium">
              <span>Redução de despesas</span>
              <span className="text-muted-foreground">{formatPercent(reduzirPct)}</span>
            </label>
            <Input
              id="sim-reduzir"
              aria-label="Percentual de redução de despesas"
              type="range"
              min={0}
              max={50}
              step={5}
              value={reduzirPct}
              onChange={(e) => setReduzirPct(Number(e.target.value))}
            />
            <p className="text-xs text-muted-foreground">
              Base: {formatCurrency(despesas)} de despesas no período
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          testId="simulador-atual"
          title="Resultado atual"
          value={formatCurrency(resultadoAtual)}
          icon={Wallet}
          emphasis={resultadoAtual >= 0 ? 'positive' : 'negative'}
        />
        <KpiCard
          testId="simulador-receber"
          title="+ Recebíveis"
          value={formatCurrency(aReceber)}
          icon={TrendingUp}
        />
        <KpiCard
          testId="simulador-economia"
          title="+ Economia"
          value={formatCurrency(economia)}
          icon={PiggyBank}
        />
        <KpiCard
          testId="simulador-resultado"
          title="Resultado simulado"
          value={formatCurrency(resultadoSimulado)}
          icon={Calculator}
          emphasis={resultadoSimulado >= 0 ? 'positive' : 'negative'}
        />
      </div>

      <Alert variant="info" title="Simulação">
        Cenário hipotético calculado no cliente — recebíveis em aberto e despesas do período
        selecionado. Nada é gravado.
      </Alert>
    </div>
  )
}
