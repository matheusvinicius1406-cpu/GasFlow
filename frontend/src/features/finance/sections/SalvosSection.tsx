import { useId, useState } from 'react'
import { Bookmark, Plus, Trash2 } from 'lucide-react'
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
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { formatDateTime } from '@/lib/utils'
import type { SavedReport } from '../useAnalyticsData'
import { SECTIONS } from '../usePeriodFilter'

/**
 * Relatórios salvos (P8) — lista/cria/remove snapshots de configuração de
 * relatório (`finance_saved_reports`). Escrita gated por `finance.write`
 * (V3) e confirmação de exclusão em `Dialog` (nunca `window.confirm`).
 */
export function SalvosSection({
  data,
  canWrite,
  saving,
  onCreate,
  onDelete,
}: {
  data: SavedReport[]
  canWrite: boolean
  saving: boolean
  onCreate: (name: string, reportType: string) => Promise<boolean>
  onDelete: (report: SavedReport) => Promise<boolean>
}) {
  const nameId = useId()
  const typeId = useId()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', reportType: SECTIONS[0]?.slug ?? 'visao-geral' })
  const [confirmTarget, setConfirmTarget] = useState<SavedReport | null>(null)

  const labelDe = (slug: string) => SECTIONS.find((s) => s.slug === slug)?.label ?? slug

  async function salvar() {
    if (!form.name.trim()) return
    const ok = await onCreate(form.name.trim(), form.reportType)
    if (ok) {
      setOpen(false)
      setForm({ name: '', reportType: SECTIONS[0]?.slug ?? 'visao-geral' })
    }
  }

  async function confirmarExclusao() {
    if (!confirmTarget) return
    const ok = await onDelete(confirmTarget)
    if (ok) setConfirmTarget(null)
  }

  return (
    <div className="space-y-6" data-testid="salvos-section">
      <Card data-testid="salvos-lista">
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Relatórios salvos</CardTitle>
          {canWrite && (
            <Button type="button" size="sm" onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" />
              Novo
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {data.length === 0 ? (
            <EmptyState
              icon={Bookmark}
              title="Nenhum relatório salvo"
              description={
                canWrite
                  ? 'Salve uma configuração de relatório para reabrir depois.'
                  : 'Nenhum relatório salvo neste tenant.'
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Criado por</TableHead>
                    <TableHead>Criado em</TableHead>
                    <TableHead>Ação</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-medium">{item.name}</TableCell>
                      <TableCell>{labelDe(item.report_type)}</TableCell>
                      <TableCell className="font-mono text-xs">{item.created_by ?? '—'}</TableCell>
                      <TableCell>{formatDateTime(item.created_at)}</TableCell>
                      <TableCell>
                        {canWrite && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="text-destructive hover:bg-destructive/10"
                            aria-label={`Remover ${item.name}`}
                            onClick={() => setConfirmTarget(item)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Novo relatório salvo</DialogTitle>
            <DialogDescription>Dá um nome e escolhe a seção de referência.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor={nameId} className="text-sm font-medium text-foreground">
                Nome
              </label>
              <Input
                id={nameId}
                aria-label="Nome do relatório"
                placeholder="Ex.: Fechamento de setembro"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor={typeId} className="text-sm font-medium text-foreground">
                Tipo
              </label>
              <Select
                id={typeId}
                aria-label="Tipo do relatório"
                value={form.reportType}
                onChange={(e) => setForm({ ...form, reportType: e.target.value })}
              >
                {SECTIONS.map((s) => (
                  <option key={s.slug} value={s.slug}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <DialogFooter>
            <DialogClose>Cancelar</DialogClose>
            <Button
              type="button"
              onClick={() => void salvar()}
              disabled={saving || !form.name.trim()}
            >
              {saving ? 'Salvando…' : 'Salvar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={confirmTarget !== null}
        onOpenChange={(next) => {
          if (!next) setConfirmTarget(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remover relatório?</DialogTitle>
            <DialogDescription>
              {confirmTarget ? `"${confirmTarget.name}" será removido. Não dá para desfazer.` : ''}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose>Voltar</DialogClose>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void confirmarExclusao()}
              disabled={saving}
            >
              Remover
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
