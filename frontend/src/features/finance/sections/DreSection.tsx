import { BarChart3, TrendingDown, TrendingUp, Wallet } from 'lucide-react'
import { Alert } from '@/components/ui/Alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { cn, formatCurrency, formatPercent } from '@/lib/utils'
import { CATEGORY_LABELS } from '../financeLabels'
import type { DreData } from '../useAnalyticsData'
import { money } from '../useVisaoGeralData'
import { KpiCard } from './KpiCard'

type Linha = { label: string; value: number; kind: 'in' | 'out' | 'total' }

/**
 * DRE Gerencial (P6) — apresentacional: o shell busca e injeta. Mostra a
 * cascata receita → CMV → lucro bruto → despesas → resultado e o rótulo
 * honesto da cobertura do CMV (`cmv_coverage`), já que produtos sem nota de
 * compra confirmada entram sem custo.
 */
export function DreSection({ data }: { data: DreData }) {
  const revenue = money(data.revenue)
  const cmv = money(data.cmv)
  const gross = money(data.gross_profit)
  const expenses = money(data.expenses)
  const result = money(data.result)
  const coverage = data.cmv_coverage
  const coberturaParcial = coverage !== null && coverage < 100

  const linhas: Linha[] = [
    { label: 'Receita bruta', value: revenue, kind: 'in' },
    { label: '(−) CMV', value: cmv, kind: 'out' },
    { label: '= Lucro bruto', value: gross, kind: 'total' },
    { label: '(−) Despesas operacionais', value: expenses, kind: 'out' },
    { label: '= Resultado', value: result, kind: 'total' },
  ]

  return (
    <div className="space-y-6" data-testid="dre-section">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          testId="dre-receita"
          title="Receita bruta"
          value={formatCurrency(revenue)}
          icon={TrendingUp}
        />
        <KpiCard
          testId="dre-lucro-bruto"
          title="Lucro bruto"
          value={formatCurrency(gross)}
          icon={BarChart3}
          emphasis={gross >= 0 ? 'positive' : 'negative'}
        />
        <KpiCard
          testId="dre-despesas"
          title="Despesas operacionais"
          value={formatCurrency(expenses)}
          icon={TrendingDown}
        />
        <KpiCard
          testId="dre-resultado"
          title="Resultado"
          value={formatCurrency(result)}
          icon={Wallet}
          emphasis={result >= 0 ? 'positive' : 'negative'}
        />
      </div>

      {coberturaParcial && (
        <Alert variant="warning" title="CMV parcial">
          Só {formatPercent(coverage ?? 0)} da receita tem custo conhecido. Produtos sem nota de
          compra confirmada entram com custo zero — confirme as notas de compra para o CMV ficar
          completo.
        </Alert>
      )}

      <Card data-testid="dre-cascata">
        <CardHeader>
          <CardTitle className="text-base">Demonstrativo do período</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Linha</TableHead>
                <TableHead className="text-right">Valor</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {linhas.map((linha) => (
                <TableRow key={linha.label}>
                  <TableCell className={cn(linha.kind === 'total' && 'font-semibold')}>
                    {linha.label}
                  </TableCell>
                  <TableCell
                    className={cn(
                      'text-right',
                      linha.kind === 'in'
                        ? 'text-success'
                        : linha.kind === 'out'
                          ? 'text-destructive'
                          : 'font-semibold text-foreground'
                    )}
                  >
                    {linha.kind === 'out' && linha.value > 0 ? '−' : ''}
                    {formatCurrency(linha.value)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell className="font-semibold">Receita no período</TableCell>
                <TableCell className="text-right font-semibold">
                  {formatCurrency(revenue)}
                </TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </CardContent>
      </Card>

      <Card data-testid="dre-despesas-categoria">
        <CardHeader>
          <CardTitle className="text-base">Despesas por categoria</CardTitle>
        </CardHeader>
        <CardContent>
          {data.expense_items.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nenhuma despesa operacional no período.
            </p>
          ) : (
            <div className="space-y-3">
              {data.expense_items.map((item) => {
                const total = money(item.total)
                const pct = item.pct ?? 0
                return (
                  <div key={item.category} className="space-y-1">
                    <div className="flex items-baseline justify-between gap-2 text-sm">
                      <span className="font-medium">
                        {CATEGORY_LABELS[item.category] ?? item.category}
                      </span>
                      <span className="text-muted-foreground">
                        {formatCurrency(total)}
                        {item.pct !== null && (
                          <span className="ml-2 text-xs">{formatPercent(pct)}</span>
                        )}
                      </span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-destructive"
                        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
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
