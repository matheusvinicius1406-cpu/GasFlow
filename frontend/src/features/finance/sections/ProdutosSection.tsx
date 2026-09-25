import { AlertTriangle, Boxes, DollarSign, TrendingUp } from 'lucide-react'
import { Alert } from '@/components/ui/Alert'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { cn, formatCurrency, formatNumber, formatPercent } from '@/lib/utils'
import type { ProductsData } from '../useAnalyticsData'
import { money } from '../useVisaoGeralData'
import { KpiCard } from './KpiCard'

/**
 * Produtos (P6) — margem por produto. O rótulo honesto vem da API: quando o
 * produto não tem nota de compra CONFIRMED, `cost_known = false` e a margem
 * é `null` (a linha mostra "Sem custo", nunca zero disfarçado).
 */
export function ProdutosSection({ data }: { data: ProductsData }) {
  const items = data.items
  const receita = money(data.revenue)
  const quantidade = items.reduce((s, i) => s + i.quantity, 0)
  const margemConhecida = items.reduce((s, i) => s + (i.cost_known ? money(i.margin) : 0), 0)
  const semCusto = items.filter((i) => !i.cost_known).length

  return (
    <div className="space-y-6" data-testid="produtos-section">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          testId="produtos-receita"
          title="Receita de produtos"
          value={formatCurrency(receita)}
          icon={TrendingUp}
        />
        <KpiCard
          testId="produtos-margem"
          title="Margem conhecida"
          value={formatCurrency(margemConhecida)}
          icon={DollarSign}
          emphasis={margemConhecida >= 0 ? 'positive' : 'negative'}
        />
        <KpiCard
          testId="produtos-itens"
          title="Itens vendidos"
          value={formatNumber(quantidade)}
          icon={Boxes}
        />
        <KpiCard
          testId="produtos-sem-custo"
          title="Produtos sem custo"
          value={formatNumber(semCusto)}
          icon={AlertTriangle}
          emphasis={semCusto > 0 ? 'negative' : undefined}
        />
      </div>

      {semCusto > 0 && (
        <Alert variant="warning" title="Margem incompleta">
          {semCusto} produto{semCusto === 1 ? '' : 's'} sem nota de compra confirmada. Para esses, a
          margem fica indisponível até a nota ser confirmada.
        </Alert>
      )}

      <Card data-testid="produtos-tabela">
        <CardHeader>
          <CardTitle className="text-base">Margem por produto</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Produto</TableHead>
                  <TableHead className="text-right">Qtd</TableHead>
                  <TableHead className="text-right">Receita</TableHead>
                  <TableHead className="text-right">Custo unit.</TableHead>
                  <TableHead className="text-right">Margem</TableHead>
                  <TableHead className="text-right">Margem %</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.product_codigo}>
                    <TableCell>
                      <div className="font-medium">{item.product_nome}</div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {item.product_codigo}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">{formatNumber(item.quantity)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(money(item.revenue))}</TableCell>
                    <TableCell className="text-right">
                      {item.unit_cost === null ? '—' : formatCurrency(money(item.unit_cost))}
                    </TableCell>
                    <TableCell
                      className={cn(
                        'text-right',
                        item.cost_known
                          ? money(item.margin) >= 0
                            ? 'text-success'
                            : 'text-destructive'
                          : 'text-muted-foreground'
                      )}
                    >
                      {item.cost_known ? formatCurrency(money(item.margin)) : '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      {item.cost_known ? (
                        item.margin_pct === null ? (
                          '—'
                        ) : (
                          formatPercent(item.margin_pct)
                        )
                      ) : (
                        <Badge variant="secondary">Sem custo</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
