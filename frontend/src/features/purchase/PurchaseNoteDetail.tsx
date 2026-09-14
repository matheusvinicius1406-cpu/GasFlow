import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { api } from '@/lib/api/client'
import type { PurchaseNote } from './PurchaseNotesPage'
import { STATUS_LABEL, formatCents, statusVariant } from './PurchaseNotesPage'

export function PurchaseNoteDetail({
  noteId,
  onClose,
  onConfirm,
  onCancel,
  canConfirm,
  canCancel,
  busy,
}: {
  noteId: string
  onClose: () => void
  onConfirm: () => void
  onCancel: () => void
  canConfirm: boolean
  canCancel: boolean
  busy: boolean
}) {
  const [note, setNote] = useState<PurchaseNote | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    api.purchaseNotes
      .get(noteId)
      .then(({ data }) => setNote(data))
      .catch(() => setError(true))
  }, [noteId])

  if (error) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
        <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6">
          <p role="alert" className="text-sm text-destructive">Erro ao carregar nota.</p>
          <Button variant="outline" className="mt-4" onClick={onClose}>
            Fechar
          </Button>
        </div>
      </div>
    )
  }

  if (!note) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-lg border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Nota #{note.note_number}</h2>
          <Badge variant={statusVariant(note.status)}>{STATUS_LABEL[note.status]}</Badge>
        </div>

        <dl className="mb-4 grid grid-cols-2 gap-2 text-sm">
          <div>
            <dt className="text-muted-foreground">Fornecedor</dt>
            <dd className="font-medium">{note.supplier_name}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">CNPJ</dt>
            <dd>{note.supplier_cnpj || '—'}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Data de emissão</dt>
            <dd>{note.issue_date?.slice(0, 10)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Total</dt>
            <dd className="font-semibold">{formatCents(note.total_cents)}</dd>
          </div>
        </dl>

        {note.observations && <p className="mb-4 text-sm text-muted-foreground">{note.observations}</p>}

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="py-2">Produto</th>
              <th className="py-2 text-right">Qtd</th>
              <th className="py-2 text-right">Unitário</th>
              <th className="py-2 text-right">Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {(note.items ?? []).map((i) => (
              <tr key={i.product_codigo} className="border-b border-border/50">
                <td className="py-2">{i.product_name || i.product_codigo}</td>
                <td className="py-2 text-right">{i.quantity}</td>
                <td className="py-2 text-right">{formatCents(i.unit_price_cents)}</td>
                <td className="py-2 text-right">{formatCents(i.subtotal_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>
          {canCancel && (
            <Button variant="outline" onClick={onCancel} disabled={busy}>
              Cancelar nota
            </Button>
          )}
          {canConfirm && (
            <Button onClick={onConfirm} disabled={busy}>
              {busy ? <LoadingSpinner className="h-4 w-4" /> : 'Confirmar e entrar estoque'}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
