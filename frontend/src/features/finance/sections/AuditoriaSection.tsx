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
import { formatDateTime } from '@/lib/utils'
import type { AuditData } from '../useAnalyticsData'

const RESOURCE_LABELS: Record<string, string> = {
  payment: 'Pagamento',
  expense: 'Despesa',
  budget: 'Orçamento',
  saved_report: 'Relatório salvo',
  cash_movement: 'Caixa',
  receivable: 'Recebível',
}

/**
 * Auditoria financeira (P8) — trilha de `auth_audit_log` das mutações do
 * Financeiro. Sem backfill: só eventos a partir do deploy. Leitura exige
 * `audit.view` (a seção fica oculta sem a permissão).
 */
export function AuditoriaSection({ data }: { data: AuditData }) {
  return (
    <div className="space-y-6" data-testid="auditoria-section">
      <Alert variant="info" title="Trilha sem backfill">
        Registra apenas eventos a partir do deploy da Central Financeira — lançamentos anteriores não
        aparecem aqui.
      </Alert>

      <Card data-testid="auditoria-tabela">
        <CardHeader>
          <CardTitle className="text-base">
            Últimos eventos ({data.total} em {data.days} dia{data.days === 1 ? '' : 's'})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data/hora</TableHead>
                  <TableHead>Ação</TableHead>
                  <TableHead>Recurso</TableHead>
                  <TableHead>ID</TableHead>
                  <TableHead>Ator</TableHead>
                  <TableHead>Resultado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="whitespace-nowrap">
                      {formatDateTime(item.timestamp)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{item.action}</TableCell>
                    <TableCell>{RESOURCE_LABELS[item.resource] ?? item.resource}</TableCell>
                    <TableCell className="font-mono text-xs">{item.resource_id}</TableCell>
                    <TableCell className="font-mono text-xs">{item.actor_id}</TableCell>
                    <TableCell>
                      <Badge variant={item.result === 'success' ? 'success' : 'secondary'}>
                        {item.result}
                      </Badge>
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
