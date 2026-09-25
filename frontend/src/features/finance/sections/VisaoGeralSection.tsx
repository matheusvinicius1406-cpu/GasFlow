import { useId, useState, type FormEvent } from 'react'
import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  Plus,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Badge, type BadgeProps } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { Select } from '@/components/ui/Select'
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
import type { CashMovement, FinanceExpense, FinancePayment, Receivable } from '@/types'
import { chartToken, chartVar } from '../chartTokens'
import { toCsvDate } from '../exportPeriodCsv'
import { CATEGORY_LABELS, METHOD_LABELS } from '../financeLabels'
import { KpiCard } from './KpiCard'
import { money, type VisaoGeralData, type VisaoTab } from '../useVisaoGeralData'

/**
 * Seção Visão Geral (P5) — apresentacional: recebe `data` já buscado pelo
 * shell (`useVisaoGeralData`) e emite ações. Aqui vivem as 4 escritas da
 * tela (nova despesa, cancelar despesa, cancelar pagamento, registrar
 * recebimento) — todas em `Dialog` (nunca `window.confirm`) e visíveis só
 * com `finance.write`/`finance.receive` (V3).
 */

interface VisaoGeralSectionProps {
  data: VisaoGeralData
  can: { write: boolean; receive: boolean }
}

const TABS: { key: VisaoTab; label: string }[] = [
  { key: 'payments', label: 'Pagamentos' },
  { key: 'receivables', label: 'Recebíveis' },
  { key: 'expenses', label: 'Despesas' },
  { key: 'cash', label: 'Caixa' },
]

type StatusMap = Record<string, { label: string; variant: BadgeProps['variant'] }>

const PAYMENT_STATUS: StatusMap = {
  PAID: { label: 'Pago', variant: 'success' },
  PARTIAL: { label: 'Parcial', variant: 'info' },
  PENDING: { label: 'Pendente', variant: 'warning' },
  REFUNDED: { label: 'Estornado', variant: 'secondary' },
  CANCELLED: { label: 'Cancelado', variant: 'secondary' },
}

const RECEIVABLE_STATUS: StatusMap = {
  OPEN: { label: 'Aberto', variant: 'info' },
  PARTIAL: { label: 'Parcial', variant: 'warning' },
  PAID: { label: 'Pago', variant: 'success' },
  OVERDUE: { label: 'Atrasado', variant: 'destructive' },
  CANCELLED: { label: 'Cancelado', variant: 'secondary' },
}

const EXPENSE_STATUS: StatusMap = {
  ACTIVE: { label: 'Ativa', variant: 'success' },
  CANCELLED: { label: 'Cancelada', variant: 'secondary' },
}

const CASH_TYPE: StatusMap = {
  RECEIPT: { label: 'Entrada', variant: 'success' },
  EXPENSE: { label: 'Saída', variant: 'destructive' },
  REFUND: { label: 'Estorno', variant: 'warning' },
}

function statusBadge(map: StatusMap, status: string) {
  const cfg = map[status]
  return <Badge variant={cfg?.variant ?? 'secondary'}>{cfg?.label ?? status}</Badge>
}

function InsightCard({
  label,
  value,
  hint,
  emphasis,
}: {
  label: string
  value: string
  hint: string
  emphasis?: 'positive' | 'negative'
}) {
  return (
    <Card>
      <CardContent className="space-y-1 p-5">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p
          className={cn(
            'text-2xl font-bold',
            emphasis === 'negative'
              ? 'text-destructive'
              : emphasis === 'positive'
                ? 'text-success'
                : 'text-foreground'
          )}
        >
          {value}
        </p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  )
}

function MetaCard({
  budget,
  budgetFailed,
  realizado,
  days,
}: {
  budget: VisaoGeralData['budget']
  budgetFailed: boolean
  realizado: number
  days: number
}) {
  const meta = budget ? money(budget.total) : 0
  const pct = meta > 0 ? (realizado / meta) * 100 : 0
  const acima = meta > 0 && realizado > meta

  return (
    <Card data-testid="vg-meta">
      <CardHeader>
        <CardTitle className="text-base">Meta do mês</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {budgetFailed ? (
          <p className="text-sm text-muted-foreground">Orçamento indisponível no momento.</p>
        ) : meta <= 0 ? (
          <p className="text-sm text-muted-foreground">
            Sem meta definida{budget ? ` para ${String(budget.month).padStart(2, '0')}/${budget.year}` : ''}.
          </p>
        ) : (
          <>
            <div className="flex items-baseline justify-between gap-2">
              <span className={cn('text-2xl font-bold', acima ? 'text-destructive' : 'text-foreground')}>
                {formatCurrency(realizado)}
              </span>
              <span className="text-sm text-muted-foreground">de {formatCurrency(meta)}</span>
            </div>
            <div
              className="h-2 w-full overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-label="Progresso da meta do mês"
              aria-valuenow={Math.round(pct)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className={cn('h-full rounded-full', acima ? 'bg-destructive' : 'bg-primary')}
                style={{ width: `${Math.min(100, pct)}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {formatPercent(pct)} da meta{acima ? ' — acima da meta' : ''}
            </p>
          </>
        )}
        {days !== 30 && (
          <p className="text-xs text-muted-foreground">
            Orçamento = mês corrente; realizado = período selecionado.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export function VisaoGeralSection({ data, can }: VisaoGeralSectionProps) {
  const period = data.period
  const descId = useId()
  const amountId = useId()
  const categoryId = useId()
  const receiveAmountId = useId()
  const receiveMethodId = useId()

  const [expenseOpen, setExpenseOpen] = useState(false)
  const [expenseForm, setExpenseForm] = useState({ description: '', amount: '', category: 'OTHER' })
  const [confirmTarget, setConfirmTarget] = useState<
    { kind: 'expense' | 'payment'; item: FinanceExpense | FinancePayment } | null
  >(null)
  const [receiveTarget, setReceiveTarget] = useState<Receivable | null>(null)
  const [receiveForm, setReceiveForm] = useState({ amount: '', method: 'PIX' })
  const [receiveError, setReceiveError] = useState('')

  if (!period) return null

  const tab = data.table.tab
  const rec = data.recSummary
  const { actions } = data

  function submitCreate(e?: FormEvent) {
    e?.preventDefault()
    const amount = Number(expenseForm.amount.replace(',', '.'))
    if (!expenseForm.description.trim() || !Number.isFinite(amount) || amount <= 0) return
    void actions
      .createExpense({
        description: expenseForm.description.trim(),
        amount,
        category: expenseForm.category,
      })
      .then((ok) => {
        if (!ok) return
        setExpenseOpen(false)
        setExpenseForm({ description: '', amount: '', category: 'OTHER' })
      })
  }

  function submitConfirm() {
    if (!confirmTarget) return
    const run =
      confirmTarget.kind === 'expense'
        ? actions.cancelExpense(confirmTarget.item as FinanceExpense)
        : actions.cancelPayment(confirmTarget.item as FinancePayment)
    void run.then((ok) => {
      if (ok) setConfirmTarget(null)
    })
  }

  function submitReceive(e?: FormEvent) {
    e?.preventDefault()
    if (!receiveTarget) return
    const amount = Number(receiveForm.amount.replace(',', '.'))
    const restante = money(receiveTarget.remaining_amount)
    if (!Number.isFinite(amount) || amount <= 0) {
      setReceiveError('Informe um valor maior que zero.')
      return
    }
    if (amount > restante + 1e-6) {
      setReceiveError(`Até ${formatCurrency(restante)} (restante do pedido).`)
      return
    }
    setReceiveError('')
    void actions.registerReceive(receiveTarget.order_codigo, { amount, method: receiveForm.method }).then((ok) => {
      if (!ok) return
      setReceiveTarget(null)
      setReceiveError('')
    })
  }

  function SortHead({ label, field, className }: { label: string; field: string; className?: string }) {
    const active = data.table.orderBy === field
    return (
      <TableHead className={className}>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-sm font-medium hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => actions.toggleSort(field)}
          aria-label={`Ordenar por ${label}`}
        >
          {label}
          {active &&
            (data.table.order === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
        </button>
      </TableHead>
    )
  }

  const payments = data.table.items as FinancePayment[]
  const receivables = data.table.items as Receivable[]
  const expenses = data.table.items as FinanceExpense[]
  const cashMovements = data.table.items as CashMovement[]
  const rowsEmpty = data.table.items.length === 0

  const confirmPendingKey =
    confirmTarget === null
      ? null
      : confirmTarget.kind === 'expense'
        ? `expense-${confirmTarget.item.id}`
        : `payment-${confirmTarget.item.id}`

  const donutData = (data.categories?.items ?? [])
    .map((c) => ({ name: CATEGORY_LABELS[c.category] ?? c.category, value: money(c.total) }))
    .filter((d) => d.value > 0)

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Recebimentos"
          value={formatCurrency(money(period.total_receipts))}
          icon={TrendingUp}
          delta={period.comparison.receipts_pct}
        />
        <KpiCard
          title="Despesas"
          value={formatCurrency(money(period.total_expenses))}
          icon={TrendingDown}
          delta={period.comparison.expenses_pct}
          invertDelta
        />
        <KpiCard
          title="Resultado"
          value={formatCurrency(money(period.net_result))}
          icon={BarChart3}
          delta={period.comparison.net_pct}
          emphasis={money(period.net_result) >= 0 ? 'positive' : 'negative'}
        />
        <KpiCard title="Saldo em Caixa" value={formatCurrency(data.balance ?? 0)} icon={Wallet} />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <InsightCard
          label="A receber"
          value={rec ? formatCurrency(money(rec.open_total)) : '—'}
          hint={
            rec
              ? `${rec.open_count} título${rec.open_count === 1 ? '' : 's'} em aberto`
              : data.recSummaryFailed
                ? 'Resumo indisponível'
                : 'Carregando…'
          }
        />
        <InsightCard
          label="Em atraso"
          value={rec ? formatCurrency(money(rec.overdue_total)) : '—'}
          hint={
            rec
              ? `${rec.overdue_count} vencido${rec.overdue_count === 1 ? '' : 's'}`
              : data.recSummaryFailed
                ? 'Resumo indisponível'
                : 'Carregando…'
          }
          emphasis={rec && money(rec.overdue_total) > 0 ? 'negative' : undefined}
        />
        <InsightCard
          label="Recebido hoje"
          value={data.todayReceived !== null ? formatCurrency(data.todayReceived) : '—'}
          hint={data.dashboardFailed ? 'Dashboard indisponível' : 'Total recebido hoje'}
          emphasis={data.todayReceived !== null && data.todayReceived > 0 ? 'positive' : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <MetaCard
          budget={data.budget}
          budgetFailed={data.budgetFailed}
          realizado={money(period.total_expenses)}
          days={period.days}
        />
        <Card className="lg:col-span-2" data-testid="vg-fluxo">
          <CardHeader>
            <CardTitle className="text-base">Entradas, saídas e resultado por dia</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={period.daily} margin={{ top: 5, right: 12, left: -12, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d: string) => toCsvDate(d).slice(0, 5)} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(value) => formatCurrency(Number(value))}
                  labelFormatter={(label) => toCsvDate(String(label))}
                />
                <Legend />
                <Bar dataKey="receipts" name="Recebimentos" fill={chartVar('--success')} radius={[3, 3, 0, 0]} />
                <Bar dataKey="expenses" name="Despesas" fill={chartVar('--destructive')} radius={[3, 3, 0, 0]} />
                <Line type="monotone" dataKey="net_result" name="Resultado" stroke={chartVar('--info')} strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card data-testid="vg-categorias">
        <CardHeader>
          <CardTitle className="text-base">Despesas por categoria</CardTitle>
        </CardHeader>
        <CardContent>
          {data.categoriesFailed ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Não foi possível carregar as categorias.
            </p>
          ) : data.categories === null ? (
            <div className="flex justify-center py-8">
              <LoadingSpinner />
            </div>
          ) : donutData.length === 0 ? (
            <EmptyState
              icon={BarChart3}
              title="Sem despesas por categoria"
              description="Nenhuma despesa ativa no período escolhido."
            />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={donutData} dataKey="value" nameKey="name" innerRadius={70} outerRadius={110} paddingAngle={2}>
                  {donutData.map((entry, i) => (
                    <Cell key={entry.name} fill={chartToken(i)} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => formatCurrency(Number(value))} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card data-testid="vg-tabela">
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Movimentações</CardTitle>
          <div className="flex items-center gap-2">
            <Input
              aria-label="Buscar movimentações"
              placeholder="Buscar…"
              className="h-9 w-44"
              value={data.table.q}
              onChange={(e) => actions.setQ(e.target.value)}
            />
            {can.write && (
              <Button
                size="sm"
                type="button"
                onClick={() => setExpenseOpen(true)}
                disabled={data.pending === 'create-expense'}
              >
                <Plus className="h-4 w-4" />
                Nova despesa
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-1" role="group" aria-label="Tipo de movimentação">
            {TABS.map((t) => (
              <Button
                key={t.key}
                size="sm"
                type="button"
                variant={tab === t.key ? 'default' : 'outline'}
                aria-pressed={tab === t.key}
                onClick={() => actions.selectTab(t.key)}
              >
                {t.label}
              </Button>
            ))}
          </div>

          {data.table.error ? (
            <ErrorState
              message="Não foi possível carregar as movimentações."
              onRetry={() => void actions.reload()}
            />
          ) : data.table.loading && rowsEmpty ? (
            <div className="flex justify-center py-10">
              <LoadingSpinner />
            </div>
          ) : rowsEmpty ? (
            <EmptyState
              icon={BarChart3}
              title="Nenhuma movimentação"
              description="Ajuste a busca ou o período para ver registros."
            />
          ) : (
            <div className="max-h-96 overflow-auto">
              {tab === 'payments' && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <SortHead label="Pedido" field="order_codigo" />
                      <SortHead label="Data" field="created_at" />
                      <SortHead label="Valor" field="amount" className="text-right" />
                      <SortHead label="Forma" field="method" />
                      <SortHead label="Status" field="status" />
                      <TableHead>Ação</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {payments.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell className="font-mono">#{p.order_codigo}</TableCell>
                        <TableCell>{toCsvDate((p.paid_at ?? p.created_at).slice(0, 10))}</TableCell>
                        <TableCell className="text-right text-success">{formatCurrency(money(p.amount))}</TableCell>
                        <TableCell>{METHOD_LABELS[p.method] ?? p.method}</TableCell>
                        <TableCell>{statusBadge(PAYMENT_STATUS, p.status)}</TableCell>
                        <TableCell>
                          {can.write && p.status !== 'REFUNDED' && String(p.status) !== 'CANCELLED' && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="text-destructive hover:bg-destructive/10"
                              aria-label={`Cancelar pagamento do pedido ${p.order_codigo}`}
                              disabled={data.pending === `payment-${p.id}`}
                              onClick={() => setConfirmTarget({ kind: 'payment', item: p })}
                            >
                              {data.pending === `payment-${p.id}` ? 'Cancelando…' : 'Cancelar'}
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}

              {tab === 'receivables' && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Pedido</TableHead>
                      <SortHead label="Cliente" field="customer_codigo" />
                      <SortHead label="Vencimento" field="due_date" />
                      <SortHead label="Original" field="original_amount" className="text-right" />
                      <TableHead className="text-right">Restante</TableHead>
                      <SortHead label="Status" field="status" />
                      <TableHead>Ação</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {receivables.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="font-mono">#{r.order_codigo}</TableCell>
                        <TableCell>{r.customer_codigo}</TableCell>
                        <TableCell>{r.due_date ? toCsvDate(r.due_date) : '—'}</TableCell>
                        <TableCell className="text-right">{formatCurrency(money(r.original_amount))}</TableCell>
                        <TableCell className="text-right">{formatCurrency(money(r.remaining_amount))}</TableCell>
                        <TableCell>{statusBadge(RECEIVABLE_STATUS, r.status)}</TableCell>
                        <TableCell>
                          {can.receive && ['OPEN', 'PARTIAL', 'OVERDUE'].includes(r.status) && (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              aria-label={`Registrar pagamento do pedido ${r.order_codigo}`}
                              onClick={() => {
                                setReceiveForm({ amount: String(r.remaining_amount), method: 'PIX' })
                                setReceiveError('')
                                setReceiveTarget(r)
                              }}
                            >
                              Registrar pagamento
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}

              {tab === 'expenses' && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <SortHead label="Data" field="date" />
                      <SortHead label="Descrição" field="description" />
                      <SortHead label="Categoria" field="category" />
                      <SortHead label="Valor" field="amount" className="text-right" />
                      <TableHead>Status</TableHead>
                      <TableHead>Ação</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {expenses.map((e) => (
                      <TableRow key={e.id}>
                        <TableCell>{toCsvDate(e.date.slice(0, 10))}</TableCell>
                        <TableCell>{e.description}</TableCell>
                        <TableCell>{CATEGORY_LABELS[e.category] ?? e.category}</TableCell>
                        <TableCell className="text-right text-destructive">{formatCurrency(money(e.amount))}</TableCell>
                        <TableCell>{statusBadge(EXPENSE_STATUS, e.status)}</TableCell>
                        <TableCell>
                          {can.write && e.status === 'ACTIVE' && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="text-destructive hover:bg-destructive/10"
                              aria-label={`Cancelar despesa ${e.description}`}
                              disabled={data.pending === `expense-${e.id}`}
                              onClick={() => setConfirmTarget({ kind: 'expense', item: e })}
                            >
                              {data.pending === `expense-${e.id}` ? 'Cancelando…' : 'Cancelar'}
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}

              {tab === 'cash' && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <SortHead label="Data" field="created_at" />
                      <TableHead>Histórico</TableHead>
                      <SortHead label="Tipo" field="type" />
                      <SortHead label="Valor" field="amount" className="text-right" />
                      <SortHead label="Saldo" field="balance_after" className="text-right" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {cashMovements.map((c) => (
                      <TableRow key={c.id}>
                        <TableCell>{toCsvDate(c.created_at.slice(0, 10))}</TableCell>
                        <TableCell>{c.description}</TableCell>
                        <TableCell>{statusBadge(CASH_TYPE, c.type)}</TableCell>
                        <TableCell
                          className={cn(
                            'text-right',
                            c.type === 'EXPENSE'
                              ? 'text-destructive'
                              : c.type === 'RECEIPT'
                                ? 'text-success'
                                : 'text-foreground'
                          )}
                        >
                          {formatCurrency(money(c.amount))}
                        </TableCell>
                        <TableCell className="text-right">{formatCurrency(money(c.balance_after))}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                  <TableFooter>
                    <TableRow>
                      <TableCell colSpan={4} className="font-semibold">
                        Saldo atual
                      </TableCell>
                      <TableCell className="text-right font-semibold">
                        {formatCurrency(data.balance ?? 0)}
                      </TableCell>
                    </TableRow>
                  </TableFooter>
                </Table>
              )}
            </div>
          )}

          {!data.table.error && !rowsEmpty && (
            <div className="flex flex-wrap items-center justify-between gap-2 pt-2 text-sm text-muted-foreground">
              <span>
                {data.table.total} registro{data.table.total === 1 ? '' : 's'} · página {data.table.page} de{' '}
                {Math.max(1, data.table.totalPages)}
              </span>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={data.table.page <= 1 || data.table.loading}
                  onClick={() => actions.setPage(data.table.page - 1)}
                >
                  Anterior
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={data.table.page >= data.table.totalPages || data.table.loading}
                  onClick={() => actions.setPage(data.table.page + 1)}
                >
                  Próxima
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Nova despesa — Dialog, nunca window.confirm */}
      <Dialog open={expenseOpen} onOpenChange={setExpenseOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nova despesa</DialogTitle>
            <DialogDescription>Registra uma saída de caixa como despesa ativa.</DialogDescription>
          </DialogHeader>
          <form onSubmit={(e) => void submitCreate(e)} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor={descId} className="text-sm font-medium text-foreground">
                Descrição
              </label>
              <Input
                id={descId}
                aria-label="Descrição da despesa"
                placeholder="Ex.: Gasolina"
                value={expenseForm.description}
                onChange={(e) => setExpenseForm({ ...expenseForm, description: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor={amountId} className="text-sm font-medium text-foreground">
                Valor (R$)
              </label>
              <Input
                id={amountId}
                aria-label="Valor da despesa em reais"
                type="number"
                step="0.01"
                min="0.01"
                placeholder="0,00"
                value={expenseForm.amount}
                onChange={(e) => setExpenseForm({ ...expenseForm, amount: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor={categoryId} className="text-sm font-medium text-foreground">
                Categoria
              </label>
              <Select
                id={categoryId}
                aria-label="Categoria da despesa"
                value={expenseForm.category}
                onChange={(e) => setExpenseForm({ ...expenseForm, category: e.target.value })}
              >
                {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </Select>
            </div>
          </form>
          <DialogFooter>
            <DialogClose>Cancelar</DialogClose>
            <Button type="button" onClick={() => submitCreate()} disabled={data.pending === 'create-expense'}>
              {data.pending === 'create-expense' ? 'Registrando…' : 'Registrar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmação de cancelamento — Dialog no lugar de window.confirm */}
      <Dialog
        open={confirmTarget !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmTarget(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {confirmTarget?.kind === 'expense' ? 'Cancelar despesa?' : 'Cancelar pagamento?'}
            </DialogTitle>
            <DialogDescription>
              {confirmTarget?.kind === 'expense'
                ? `A despesa "${(confirmTarget.item as FinanceExpense).description}" sai do total e do caixa. O registro continua no histórico.`
                : confirmTarget
                  ? `O pagamento de ${formatCurrency(money((confirmTarget.item as FinancePayment).amount))} do pedido #${(confirmTarget.item as FinancePayment).order_codigo} é estornado do caixa.`
                  : ''}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose>Voltar</DialogClose>
            <Button
              type="button"
              variant="destructive"
              onClick={submitConfirm}
              disabled={confirmPendingKey !== null && data.pending === confirmPendingKey}
            >
              Confirmar cancelamento
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Registrar recebimento de um recebível */}
      <Dialog
        open={receiveTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setReceiveTarget(null)
            setReceiveError('')
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar recebimento</DialogTitle>
            <DialogDescription>
              {receiveTarget
                ? `Pedido #${receiveTarget.order_codigo} · restante ${formatCurrency(money(receiveTarget.remaining_amount))}`
                : ''}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={(e) => void submitReceive(e)} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor={receiveAmountId} className="text-sm font-medium text-foreground">
                Valor recebido (R$)
              </label>
              <Input
                id={receiveAmountId}
                aria-label="Valor do recebimento em reais"
                type="number"
                step="0.01"
                min="0.01"
                value={receiveForm.amount}
                onChange={(e) => setReceiveForm({ ...receiveForm, amount: e.target.value })}
              />
              {receiveError && (
                <p className="text-sm text-destructive" role="alert">
                  {receiveError}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <label htmlFor={receiveMethodId} className="text-sm font-medium text-foreground">
                Forma
              </label>
              <Select
                id={receiveMethodId}
                aria-label="Forma de pagamento"
                value={receiveForm.method}
                onChange={(e) => setReceiveForm({ ...receiveForm, method: e.target.value })}
              >
                {Object.entries(METHOD_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </Select>
            </div>
          </form>
          <DialogFooter>
            <DialogClose>Voltar</DialogClose>
            <Button
              type="button"
              onClick={() => submitReceive()}
              disabled={receiveTarget !== null && data.pending === `receive-${receiveTarget.order_codigo}`}
            >
              Registrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
