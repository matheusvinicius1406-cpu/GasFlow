import { CreditCard, DollarSign, Layers } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { METHOD_LABELS } from '../financeLabels'
import { chartToken } from '../chartTokens'
import type { MethodBreakdownData } from '../useAnalyticsData'
import { money } from '../useVisaoGeralData'
import { KpiCard } from './KpiCard'

/**
 * Pagamentos por forma (P7) — recebido por método no período, com a fatia
 * de cada forma. Lê `/finance/reports/methods` (fecha a agregação que na
 * Visão Geral era feita sobre a página da lista).
 */
export function PagamentosSection({ data }: { data: MethodBreakdownData }) {
  const items = [...data.items].sort((a, b) => money(b.total) - money(a.total))
  const total = money(data.total)
  const principal = items[0]

  return (
    <div className="space-y-6" data-testid="pagamentos-section">
      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard
          testId="pagamentos-total"
          title="Recebido no período"
          value={formatCurrency(total)}
          icon={DollarSign}
        />
        <KpiCard
          testId="pagamentos-principal"
          title="Forma principal"
          value={principal ? (METHOD_LABELS[principal.method] ?? principal.method) : '—'}
          icon={CreditCard}
        />
        <KpiCard
          testId="pagamentos-formas"
          title="Formas usadas"
          value={items.length}
          icon={Layers}
        />
      </div>

      <Card data-testid="pagamentos-tabela">
        <CardHeader>
          <CardTitle className="text-base">Distribuição por forma</CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nenhum pagamento recebido no período.
            </p>
          ) : (
            <div className="space-y-4">
              {items.map((item, index) => {
                const valor = money(item.total)
                const pct = total > 0 ? (valor / total) * 100 : 0
                return (
                  <div key={item.method} className="space-y-1">
                    <div className="flex items-baseline justify-between gap-2 text-sm">
                      <span className="font-medium">{METHOD_LABELS[item.method] ?? item.method}</span>
                      <span className="text-muted-foreground">
                        {formatCurrency(valor)}
                        <span className="ml-2 text-xs">{formatPercent(item.pct ?? pct)}</span>
                      </span>
                    </div>
                    <div className="h-2.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${pct}%`, backgroundColor: chartToken(index) }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
