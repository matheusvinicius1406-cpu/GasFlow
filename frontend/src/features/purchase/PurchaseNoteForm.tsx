import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { api } from '@/lib/api/client'
import type { PurchaseNote, PurchaseNoteItem } from './PurchaseNotesPage'

interface Product {
  codigo: string
  nome: string
}

interface ItemForm {
  product_codigo: string
  quantity: string
  unit_price: string
}

const EMPTY_ITEM: ItemForm = { product_codigo: '', quantity: '1', unit_price: '' }

export function PurchaseNoteForm({
  note,
  onClose,
  onSaved,
}: {
  note: PurchaseNote | null
  onClose: () => void
  onSaved: (message: string) => void
}) {
  const isEdit = note != null
  const [supplierName, setSupplierName] = useState(note?.supplier_name ?? '')
  const [supplierCnpj, setSupplierCnpj] = useState(note?.supplier_cnpj ?? '')
  const [issueDate, setIssueDate] = useState(note?.issue_date?.slice(0, 10) ?? new Date().toISOString().slice(0, 10))
  const [observations, setObservations] = useState(note?.observations ?? '')
  const [items, setItems] = useState<ItemForm[]>(
    note?.items?.length
      ? note.items.map((i: PurchaseNoteItem) => ({
          product_codigo: i.product_codigo,
          quantity: String(i.quantity),
          unit_price: (i.unit_price_cents / 100).toFixed(2),
        }))
      : [{ ...EMPTY_ITEM }]
  )
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.products
      .list()
      .then(({ data }) => setProducts(data.products ?? data ?? []))
      .catch(() => setProducts([]))
  }, [])

  const setItem = (idx: number, patch: Partial<ItemForm>) => {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)))
  }

  const addItem = () => setItems((prev) => [...prev, { ...EMPTY_ITEM }])
  const removeItem = (idx: number) => setItems((prev) => prev.filter((_, i) => i !== idx))

  const total = items.reduce((acc, it) => {
    const q = Number(it.quantity) || 0
    const p = Number(it.unit_price) || 0
    return acc + q * p
  }, 0)

  const validate = (): string => {
    if (!supplierName.trim()) return 'Nome do fornecedor é obrigatório.'
    if (!issueDate) return 'Data de emissão é obrigatória.'
    if (items.length === 0) return 'Adicione pelo menos um item.'
    for (const it of items) {
      if (!it.product_codigo) return 'Selecione o produto de cada item.'
      const q = Number(it.quantity)
      if (!Number.isInteger(q) || q <= 0) return 'Quantidade deve ser inteira maior que 0.'
      if (Number(it.unit_price) < 0) return 'Preço unitário não pode ser negativo.'
    }
    return ''
  }

  const handleSubmit = async () => {
    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }
    setError('')
    setSaving(true)
    const payload = {
      supplier_name: supplierName.trim(),
      supplier_cnpj: supplierCnpj.trim() || undefined,
      issue_date: issueDate,
      observations: observations.trim() || undefined,
      items: items.map((it) => ({
        product_codigo: it.product_codigo,
        quantity: Number(it.quantity),
        unit_price: Number(it.unit_price),
      })),
    }
    try {
      if (isEdit) {
        await api.purchaseNotes.update(note.id, payload)
        onSaved(`Nota #${note.note_number} atualizada.`)
      } else {
        const { data } = await api.purchaseNotes.create(payload)
        onSaved(`Nota #${data.note_number ?? ''} criada como rascunho.`)
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Falha ao salvar nota.'
      setError(msg)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-border bg-card p-6">
        <h2 className="mb-4 text-lg font-semibold">
          {isEdit ? `Editar nota #${note.note_number}` : 'Nova nota de compra'}
        </h2>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="text-sm font-medium" htmlFor="supplier-name">
              Fornecedor *
            </label>
            <Input
              id="supplier-name"
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
              placeholder="Ex.: Marcos Gás"
            />
          </div>
          <div>
            <label className="text-sm font-medium" htmlFor="supplier-cnpj">
              CNPJ
            </label>
            <Input
              id="supplier-cnpj"
              value={supplierCnpj}
              onChange={(e) => setSupplierCnpj(e.target.value)}
              placeholder="00.000.000/0000-00"
            />
          </div>
          <div>
            <label className="text-sm font-medium" htmlFor="issue-date">
              Data de emissão *
            </label>
            <Input id="issue-date" type="date" value={issueDate} onChange={(e) => setIssueDate(e.target.value)} />
          </div>
        </div>

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium">Itens *</span>
            <Button variant="outline" size="sm" onClick={addItem}>
              + Item
            </Button>
          </div>
          {items.map((it, idx) => (
            <div key={idx} className="mb-2 grid grid-cols-[2fr_1fr_1fr_auto] items-end gap-2">
              <div>
                <label className="sr-only" htmlFor={`produto-${idx}`}>Produto</label>
                <select
                  id={`produto-${idx}`}
                  className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                  value={it.product_codigo}
                  onChange={(e) => setItem(idx, { product_codigo: e.target.value })}
                >
                  <option value="">Selecione…</option>
                  {products.map((p) => (
                    <option key={p.codigo} value={p.codigo}>
                      {p.nome} ({p.codigo})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="sr-only" htmlFor={`qtd-${idx}`}>Quantidade</label>
                <Input
                  id={`qtd-${idx}`}
                  type="number"
                  min={1}
                  step={1}
                  value={it.quantity}
                  onChange={(e) => setItem(idx, { quantity: e.target.value })}
                  placeholder="Qtd"
                />
              </div>
              <div>
                <label className="sr-only" htmlFor={`preco-${idx}`}>Preço unitário</label>
                <Input
                  id={`preco-${idx}`}
                  type="number"
                  min={0}
                  step={0.01}
                  value={it.unit_price}
                  onChange={(e) => setItem(idx, { unit_price: e.target.value })}
                  placeholder="R$"
                />
              </div>
              <Button variant="ghost" size="sm" onClick={() => removeItem(idx)} disabled={items.length === 1}>
                ✕
              </Button>
            </div>
          ))}
          <div className="mt-2 text-right text-sm font-medium">Total: R$ {total.toFixed(2).replace('.', ',')}</div>
        </div>

        <div className="mt-4">
          <label className="text-sm font-medium" htmlFor="obs">Observações</label>
          <Textarea
            id="obs"
            rows={2}
            value={observations}
            onChange={(e) => setObservations(e.target.value)}
            placeholder="Ex.: compra do dia, pagamento a prazo…"
          />
        </div>

        {error && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving ? <LoadingSpinner className="h-4 w-4" /> : isEdit ? 'Salvar' : 'Criar rascunho'}
          </Button>
        </div>
      </div>
    </div>
  )
}
