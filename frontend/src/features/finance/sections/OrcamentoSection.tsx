import { useId, useMemo, useState } from 'react'
import { Plus, Target, Trash2 } from 'lucide-react'
import { Alert } from '@/components/ui/Alert'
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
import { Input } from '@/components/ui/Input'
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
import { CATEGORY_LABELS } from '../financeLabels'
import type { BudgetSectionData } from '../useAnalyticsData'
import { money } from '../useVisaoGeralData'
import { KpiCard } from './KpiCard'

interface Linha {
  category: string
  meta: number
  realizado: number
}

/**
 * Orçamento vs. Realizado (P6 / V4) — orçamento mensal por categoria
 * (`finance_budgets`) comparado ao realizado do período. A edição substitui
 * o mês inteiro (PUT replace-all) e só aparece com `finance.write` (V3);
 * a nota de honestidade avisa quando o preset ≠ 30 dias.
 */
export function OrcamentoSection({
  data,
  days,
  canWrite,
  saving,
  onSave,
}: {
  data: BudgetSectionData
  days: number
  canWrite: boolean
  saving: boolean
  onSave: (
    year: number,
    month: number,
    items: { category: string; amount: number }[]
  ) => Promise<boolean>
}) {
  const { budget, realized } = data
  const mesLabel = `${String(budget.month).padStart(2, '0')}/${budget.year}`

  const linhas = useMemo<Linha[]>(() => {
    const mapa = new Map<string, Linha>()
    for (const item of budget.items) {
      mapa.set(item.category, { category: item.category, meta: money(item.amount), realizado: 0 })
    }
    for (const item of realized.items) {
      const atual = mapa.get(item.category)
      if (atual) atual.realizado = money(item.total)
      else mapa.set(item.category, { category: item.category, meta: 0, realizado: money(item.total) })
    }
    return [...mapa.values()]
  }, [budget.items, realized.items])

  const metaTotal = linhas.reduce((s, l) => s + l.meta, 0)
  const realizadoTotal = linhas.reduce((s, l) => s + l.realizado, 0)

  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<{ category: string; amount: string }[]>([])
  const [newCategory, setNewCategory] = useState('')
  const amountIdPrefix = useId()

  const label = (category: string) => CATEGORY_LABELS[category] ?? category

  const disponiveis = Object.keys(CATEGORY_LABELS).filter(
    (c) => !rows.some((r) => r.category === c)
  )

  function abrirEdicao() {
    setRows(
      budget.items.map((item) => ({ category: item.category, amount: String(money(item.amount)) }))
    )
    setNewCategory('')
    setOpen(true)
  }

  function adicionar() {
    if (!newCategory) return
    setRows((prev) => [...prev, { category: newCategory, amount: '' }])
    setNewCategory('')
  }

  async function salvar() {
    const items = rows
      .map((r) => ({ category: r.category, amount: Number(r.amount.replace(',', '.')) }))
      .filter((r) => Number.isFinite(r.amount) && r.amount >= 0)
    const ok = await onSave(budget.year, budget.month, items)
    if (ok) setOpen(false)
  }

  return (
    <div className="space-y-6" data-testid="orcamento-section">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <KpiCard
          testId="orcamento-meta"
          title={`Meta de ${mesLabel}`}
          value={formatCurrency(metaTotal)}
          icon={Target}
        />
        <KpiCard
          testId="orcamento-realizado"
          title="Realizado no período"
          value={formatCurrency(realizadoTotal)}
          icon={Target}
          emphasis={metaTotal > 0 && realizadoTotal > metaTotal ? 'negative' : undefined}
        />
        <KpiCard
          testId="orcamento-saldo"
          title="Saldo vs. meta"
          value={formatCurrency(metaTotal - realizadoTotal)}
          icon={Target}
          emphasis={metaTotal - realizadoTotal >= 0 ? 'positive' : 'negative'}
        />
      </div>

      {days !== 30 && (
        <Alert variant="info" title="Meta = mês corrente">
          O orçamento é mensal ({mesLabel}); o realizado segue o período selecionado (
          {days} dia{days > 1 ? 's' : ''}).
        </Alert>
      )}

      <Card data-testid="orcamento-tabela">
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Meta por categoria</CardTitle>
          {canWrite && (
            <Button type="button" size="sm" onClick={abrirEdicao}>
              <Plus className="h-4 w-4" />
              Editar orçamento
            </Button>
          )}
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Categoria</TableHead>
                <TableHead className="text-right">Meta</TableHead>
                <TableHead className="text-right">Realizado</TableHead>
                <TableHead className="text-right">Diferença</TableHead>
                <TableHead className="text-right">Uso da meta</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {linhas.map((linha) => {
                const pct = linha.meta > 0 ? (linha.realizado / linha.meta) * 100 : null
                const estourou = linha.meta > 0 && linha.realizado > linha.meta
                return (
                  <TableRow key={linha.category}>
                    <TableCell className="font-medium">{label(linha.category)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(linha.meta)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(linha.realizado)}</TableCell>
                    <TableCell
                      className={cn(
                        'text-right',
                        estourou ? 'text-destructive' : 'text-foreground'
                      )}
                    >
                      {formatCurrency(linha.meta - linha.realizado)}
                    </TableCell>
                    <TableCell className="text-right">
                      {linha.meta <= 0 ? (
                        <span className="text-xs text-muted-foreground">sem meta</span>
                      ) : (
                        <span
                          className={cn(
                            'font-medium',
                            estourou ? 'text-destructive' : 'text-success'
                          )}
                        >
                          {formatPercent(Math.min(999, pct ?? 0))}
                          {estourou ? ' — acima' : ''}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell className="font-semibold">Total</TableCell>
                <TableCell className="text-right font-semibold">{formatCurrency(metaTotal)}</TableCell>
                <TableCell className="text-right font-semibold">
                  {formatCurrency(realizadoTotal)}
                </TableCell>
                <TableCell className="text-right font-semibold">
                  {formatCurrency(metaTotal - realizadoTotal)}
                </TableCell>
                <TableCell />
              </TableRow>
            </TableFooter>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Orçamento de {mesLabel}</DialogTitle>
            <DialogDescription>
              A meta do mês é substituída por estas categorias. Valores vazios zeram a meta.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            {rows.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhuma categoria definida.</p>
            ) : (
              rows.map((row) => (
                <div key={row.category} className="flex items-center gap-2">
                  <span className="flex-1 text-sm font-medium">{label(row.category)}</span>
                  <Input
                    id={`${amountIdPrefix}-${row.category}`}
                    aria-label={`Meta de ${label(row.category)}`}
                    type="number"
                    step="0.01"
                    min="0"
                    className="h-9 w-32"
                    placeholder="0,00"
                    value={row.amount}
                    onChange={(e) =>
                      setRows((prev) =>
                        prev.map((r) =>
                          r.category === row.category ? { ...r, amount: e.target.value } : r
                        )
                      )
                    }
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={`Remover ${label(row.category)}`}
                    onClick={() => setRows((prev) => prev.filter((r) => r.category !== row.category))}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))
            )}

            {disponiveis.length > 0 && (
              <div className="flex items-center gap-2 border-t pt-3">
                <div className="flex-1">
                  <Select
                    aria-label="Categoria para adicionar"
                    className="h-9"
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                  >
                    <option value="">Adicionar categoria…</option>
                    {disponiveis.map((c) => (
                      <option key={c} value={c}>
                        {label(c)}
                      </option>
                    ))}
                  </Select>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={adicionar}
                  disabled={!newCategory}
                >
                  <Plus className="h-4 w-4" />
                  Adicionar
                </Button>
              </div>
            )}
          </div>

          <DialogFooter>
            <DialogClose>Cancelar</DialogClose>
            <Button type="button" onClick={() => void salvar()} disabled={saving}>
              {saving ? 'Salvando…' : 'Salvar orçamento'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
