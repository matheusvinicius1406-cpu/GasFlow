import { AlertTriangle, Clock, DollarSign, Users } from 'lucide-react'
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
import { cn, formatCurrency } from '@/lib/utils'
import type { ClientesData } from '../useAnalyticsData'
import { toCsvDate } from '../exportPeriodCsv'
import { money } from '../useVisaoGeralData'
import { KpiCard } from './KpiCard'

/** Ordem de exibição dos buckets de aging (a API devolve sempre os 4). */
const BUCKETS = ['0-30', '31-60', '61-90', '90+']

/** Dias de atraso a partir do vencimento (0 quando ainda não venceu). */
function diasEmAtraso(dueDate: string | null): number {
  if (!dueDate) return 0
  const due = new Date(`${dueDate.slice(0, 10)}T00:00:00`)
  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)
  return Math.max(0, Math.floor((hoje.getTime() - due.getTime()) / 86_400_000))
}

/**
 * Clientes (P7) — aging dos recebíveis em aberto e a lista de cobrança dos
 * títulos vencidos. Sem régua automática de aviso (V6, fora de escopo): a
 * lista é para ação manual.
 */
export function ClientesSection({ data }: { data: ClientesData }) {
  const { summary, overdue } = data
  const buckets = BUCKETS.map((bucket) => {
    const found = summary.buckets.find((b) => b.bucket === bucket)
    return { bucket, count: found?.count ?? 0, total: money(found?.total) }
  })
  const maxBucket = Math.max(1, ...buckets.map((b) => b.total))

  return (
    <div className="space-y-6" data-testid="clientes-section">
      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard
          testId="clientes-aberto"
          title="Em aberto"
          value={formatCurrency(money(summary.open_total))}
          icon={DollarSign}
        />
        <KpiCard
          testId="clientes-atraso"
          title="Em atraso"
          value={formatCurrency(money(summary.overdue_total))}
          icon={AlertTriangle}
          emphasis={money(summary.overdue_total) > 0 ? 'negative' : undefined}
        />
        <KpiCard
          testId="clientes-titulos"
          title="Títulos em aberto"
          value={summary.open_count}
          icon={Users}
        />
      </div>

      <Card data-testid="clientes-aging">
        <CardHeader>
          <CardTitle className="text-base">Aging por dias de atraso</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {buckets.map((b) => (
            <div key={b.bucket} className="space-y-2 rounded-lg border p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{b.bucket} dias</span>
                <span className="text-xs text-muted-foreground">
                  {b.count} título{b.count === 1 ? '' : 's'}
                </span>
              </div>
              <p className={cn('text-lg font-bold', b.total > 0 ? 'text-foreground' : 'text-muted-foreground')}>
                {formatCurrency(b.total)}
              </p>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={cn('h-full rounded-full', b.bucket === '90+' ? 'bg-destructive' : 'bg-warning')}
                  style={{ width: `${(b.total / maxBucket) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Alert variant="info" title="Ação manual">
        Coleção automática (régua de aviso) não está incluída — use esta lista para cobrar os
        títulos vencidos.
      </Alert>

      <Card data-testid="clientes-cobranca">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Clock className="h-4 w-4 text-muted-foreground" />
            Lista de cobrança (vencidos)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {overdue.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nenhum título vencido. Tudo em dia.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Pedido</TableHead>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Vencimento</TableHead>
                    <TableHead className="text-right">Atraso</TableHead>
                    <TableHead className="text-right">Restante</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {overdue.map((r) => {
                    const atraso = diasEmAtraso(r.due_date)
                    return (
                      <TableRow key={r.id}>
                        <TableCell className="font-mono">#{r.order_codigo}</TableCell>
                        <TableCell>{r.customer_codigo}</TableCell>
                        <TableCell>{r.due_date ? toCsvDate(r.due_date) : '—'}</TableCell>
                        <TableCell
                          className={cn('text-right', atraso > 0 ? 'text-destructive' : 'text-muted-foreground')}
                        >
                          {atraso} dia{atraso === 1 ? '' : 's'}
                        </TableCell>
                        <TableCell className="text-right font-semibold">
                          {formatCurrency(money(r.remaining_amount))}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
