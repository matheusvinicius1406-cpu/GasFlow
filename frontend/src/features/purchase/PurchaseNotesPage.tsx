import { useCallback, useEffect, useState } from 'react'
import { FileText, Plus, RefreshCw, Check, Ban, Pencil, FileDown, X } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { api } from '@/lib/api/client'
import { useAuth } from '@/features/auth'
import { PurchaseNoteForm } from './PurchaseNoteForm'
import { PurchaseNoteDetail } from './PurchaseNoteDetail'

export interface PurchaseNoteItem {
  id?: string
  product_codigo: string
  product_name?: string
  quantity: number
  unit_price_cents: number
  subtotal_cents: number
}

export interface PurchaseNote {
  id: string
  note_number: number
  supplier_name: string
  supplier_cnpj: string | null
  issue_date: string
  total_cents: number
  observations: string | null
  status: 'DRAFT' | 'CONFIRMED' | 'CANCELLED'
  created_at: string
  confirmed_at?: string | null
  items?: PurchaseNoteItem[]
}

const STATUS_LABEL: Record<string, string> = {
  DRAFT: 'Rascunho',
  CONFIRMED: 'Confirmada',
  CANCELLED: 'Cancelada',
}

export function statusVariant(status: string): 'secondary' | 'default' | 'destructive' {
  if (status === 'CONFIRMED') return 'default'
  if (status === 'CANCELLED') return 'destructive'
  return 'secondary'
}

function formatCents(cents: number): string {
  return `R$ ${(cents / 100).toFixed(2).replace('.', ',')}`
}

export function PurchaseNotesPage() {
  const { hasPermission } = useAuth()
  const canCreate = hasPermission('purchase.create')
  const canUpdate = hasPermission('purchase.update')
  const canConfirm = hasPermission('purchase.confirm')
  const canCancel = hasPermission('purchase.cancel')

  const [notes, setNotes] = useState<PurchaseNote[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')

  // filtros
  const [supplier, setSupplier] = useState('')
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  // modais
  const [showForm, setShowForm] = useState(false)
  const [editingNote, setEditingNote] = useState<PurchaseNote | null>(null)
  const [detailNote, setDetailNote] = useState<PurchaseNote | null>(null)

  const fetchNotes = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await api.purchaseNotes.list({
        supplier: supplier || undefined,
        status: status || undefined,
        from: from || undefined,
        to: to || undefined,
      })
      setNotes(data.notes ?? [])
      setNotice('')
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [supplier, status, from, to])

  useEffect(() => {
    fetchNotes()
  }, [fetchNotes])

  const startCreate = () => {
    setEditingNote(null)
    setShowForm(true)
  }

  const startEdit = (n: PurchaseNote) => {
    setEditingNote(n)
    setShowForm(true)
  }

  const handleConfirm = async (n: PurchaseNote) => {
    setBusy(`confirm-${n.id}`)
    setNotice('')
    try {
      await api.purchaseNotes.confirm(n.id)
      setShowForm(false)
      setDetailNote(null)
      await fetchNotes()
      setNotice(`Nota #${n.note_number} confirmada — estoque atualizado.`)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Falha ao confirmar nota.'
      setNotice(msg)
    } finally {
      setBusy('')
    }
  }

  const handleCancel = async (n: PurchaseNote) => {
    setBusy(`cancel-${n.id}`)
    setNotice('')
    try {
      await api.purchaseNotes.cancel(n.id)
      setShowForm(false)
      setDetailNote(null)
      await fetchNotes()
      setNotice(`Nota #${n.note_number} cancelada.`)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Falha ao cancelar nota.'
      setNotice(msg)
    } finally {
      setBusy('')
    }
  }

  const handlePdf = async (n: PurchaseNote) => {
    setBusy(`pdf-${n.id}`)
    try {
      const { data } = await api.purchaseNotes.get(n.id)
      // IPC desktop (printToPDF) ou fallback: abre HTML em nova aba
      const bridge = (window as { gasflow?: { exportPdf?: (html: string, name: string) => Promise<string> } })
        .gasflow
      if (bridge?.exportPdf) {
        await bridge.exportPdf(data.html, `nota-compra-${n.note_number}.pdf`)
        setNotice(`PDF da nota #${n.note_number} gerado.`)
      } else {
        const blob = new Blob([data.html], { type: 'text/html' })
        window.open(URL.createObjectURL(blob), '_blank')
      }
    } catch {
      setNotice('Falha ao gerar PDF.')
    } finally {
      setBusy('')
    }
  }

  return (
    <Page>
      <PageHeader>
        <PageTitle subtitle="Registre a compra do fornecedor para dar entrada no estoque.">
          <span className="flex items-center gap-2"><FileText className="h-6 w-6" /> Notas de Compra</span>
        </PageTitle>
        <PageActions>
          <Button variant="outline" onClick={fetchNotes} aria-label="Recarregar">
            <RefreshCw className="h-4 w-4" />
          </Button>
          {canCreate && (
            <Button onClick={startCreate}>
              <Plus className="mr-2 h-4 w-4" /> Nova nota
            </Button>
          )}
        </PageActions>
      </PageHeader>

      {notice && (
        <div role="status" className="rounded-md border border-border bg-accent/50 px-4 py-2 text-sm">
          {notice}
        </div>
      )}

      {/* Filtros */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Filtros</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-4">
          <Input
            placeholder="Fornecedor"
            value={supplier}
            onChange={(e) => setSupplier(e.target.value)}
            aria-label="Filtrar por fornecedor"
          />
          <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filtrar por status">
            <option value="">Todos os status</option>
            <option value="DRAFT">Rascunho</option>
            <option value="CONFIRMED">Confirmada</option>
            <option value="CANCELLED">Cancelada</option>
          </Select>
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="Data inicial" />
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="Data final" />
        </CardContent>
      </Card>

      {loading ? (
        <LoadingSpinner />
      ) : error ? (
        <ErrorState message="Erro ao carregar notas de compra." onRetry={fetchNotes} />
      ) : notes.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="Nenhuma nota de compra"
          description="Registre a compra do fornecedor para dar entrada no estoque."
        />
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nº</TableHead>
                  <TableHead>Fornecedor</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead>Itens</TableHead>
                  <TableHead>Total</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {notes.map((n) => (
                  <TableRow key={n.id}>
                    <TableCell className="font-medium">#{n.note_number}</TableCell>
                    <TableCell>{n.supplier_name}</TableCell>
                    <TableCell>{n.issue_date?.slice(0, 10)}</TableCell>
                    <TableCell>{n.items?.length ?? '—'}</TableCell>
                    <TableCell>{formatCents(n.total_cents)}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(n.status)}>{STATUS_LABEL[n.status]}</Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => setDetailNote(n)} aria-label="Detalhe">
                          Ver
                        </Button>
                        {canUpdate && n.status === 'DRAFT' && (
                          <Button variant="ghost" size="sm" onClick={() => startEdit(n)} aria-label="Editar">
                            <Pencil className="h-4 w-4" />
                          </Button>
                        )}
                        {canConfirm && n.status === 'DRAFT' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy === `confirm-${n.id}`}
                            onClick={() => handleConfirm(n)}
                            aria-label="Confirmar"
                          >
                            <Check className="h-4 w-4" />
                          </Button>
                        )}
                        {canCancel && n.status === 'DRAFT' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy === `cancel-${n.id}`}
                            onClick={() => handleCancel(n)}
                            aria-label="Cancelar"
                          >
                            <Ban className="h-4 w-4" />
                          </Button>
                        )}
                        {n.status === 'CONFIRMED' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy === `pdf-${n.id}`}
                            onClick={() => handlePdf(n)}
                            aria-label="PDF"
                          >
                            <FileDown className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {showForm && (
        <PurchaseNoteForm
          note={editingNote}
          onClose={() => setShowForm(false)}
          onSaved={(msg) => {
            setShowForm(false)
            fetchNotes()
            setNotice(msg)
          }}
        />
      )}

      {detailNote && (
        <PurchaseNoteDetail
          noteId={detailNote.id}
          onClose={() => setDetailNote(null)}
          onConfirm={() => handleConfirm(detailNote)}
          onCancel={() => handleCancel(detailNote)}
          canConfirm={canConfirm && detailNote.status === 'DRAFT'}
          canCancel={canCancel && detailNote.status === 'DRAFT'}
          busy={busy.startsWith('confirm-') || busy.startsWith('cancel-')}
        />
      )}
    </Page>
  )
}

export { STATUS_LABEL, formatCents }

// re-export para testes usarem X sem importar lucide direto
export const CloseIcon = X
