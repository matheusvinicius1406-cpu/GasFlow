import { CheckCircle2, Link2, SearchX } from 'lucide-react'
import { Alert } from '@/components/ui/Alert'
import { Badge, type BadgeProps } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { formatCurrency } from '@/lib/utils'
import { METHOD_LABELS } from '../financeLabels'
import type { ConciliationData } from '../useAnalyticsData'
import { money } from '../useVisaoGeralData'
import { KpiCard } from './KpiCard'

const ISSUE_LABELS: Record<string, { label: string; variant: BadgeProps['variant'] }> = {
  sem_movimento_de_caixa: { label: 'Sem movimento de caixa', variant: 'warning' },
  sem_recebivel: { label: 'Sem recebível', variant: 'destructive' },
  recebivel_em_divergencia: { label: 'Recebível em divergência', variant: 'info' },
}

/**
 * Conciliação (P8) — cruza pagamento ↔ movimento de caixa ↔ recebível. As
 * divergências são sempre "a revisar", nunca "erro": registros legados podem
 * não ter as três pontas.
 */
export function ConciliacaoSection({ data }: { data: ConciliationData }) {
  return (
    <div className="space-y-6" data-testid="conciliacao-section">
      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard testId="conciliacao-conferidos" title="Conferidos" value={data.checked} icon={Link2} />
        <KpiCard
          testId="conciliacao-conciliados"
          title="Conciliados"
          value={data.matched}
          icon={CheckCircle2}
        />
        <KpiCard
          testId="conciliacao-revisar"
          title="A revisar"
          value={data.to_review}
          icon={SearchX}
          emphasis={data.to_review > 0 ? 'negative' : undefined}
        />
      </div>

      {data.to_review === 0 ? (
        <Alert variant="success" title="Tudo conciliado">
          Nenhuma divergência entre pagamento, caixa e recebível no período.
        </Alert>
      ) : (
        <Alert variant="warning" title="Divergências a revisar">
          {data.to_review} lançamento{data.to_review === 1 ? '' : 's'} sem as três pontas completas.
          {data.note ? ` ${data.note}` : ''}
        </Alert>
      )}

      {data.items.length > 0 && (
        <Card data-testid="conciliacao-tabela">
          <CardHeader>
            <CardTitle className="text-base">Itens a revisar</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Pedido</TableHead>
                    <TableHead>Valor</TableHead>
                    <TableHead>Forma</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Pendências</TableHead>
                    <TableHead className="text-right">Δ recebível</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((item) => (
                    <TableRow key={item.payment_id}>
                      <TableCell className="font-mono">#{item.order_codigo}</TableCell>
                      <TableCell>{formatCurrency(money(item.amount))}</TableCell>
                      <TableCell>{METHOD_LABELS[item.method] ?? item.method}</TableCell>
                      <TableCell>{item.status}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {item.issues.map((issue) => {
                            const cfg = ISSUE_LABELS[issue]
                            return (
                              <Badge key={issue} variant={cfg?.variant ?? 'secondary'}>
                                {cfg?.label ?? issue}
                              </Badge>
                            )
                          })}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        {item.receivable_delta === null
                          ? '—'
                          : formatCurrency(money(item.receivable_delta))}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
