import { useCallback, useEffect, useState } from 'react'
import { Ticket, Plus, Trash2, RefreshCw, Save, X } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { apiClient } from '@/lib/api/client'

interface Coupon {
  id: string
  code: string
  name: string | null
  description: string | null
  type: string
  value: number | null
  min_order_value: number
  max_discount: number | null
  end_date: string | null
  usage_limit: number
  usage_per_customer: number
  usage_count: number
  is_active: boolean
}

interface CouponForm {
  code: string
  name: string
  type: string
  value: string
  min_order_value: string
  max_discount: string
  end_date: string
  usage_limit: string
  usage_per_customer: string
}

const COUPON_TYPES = [
  { value: 'PERCENTAGE', label: 'Percentual (%)' },
  { value: 'FIXED', label: 'Valor fixo (R$)' },
  { value: 'FREE_SHIPPING', label: 'Frete grátis' },
]

const EMPTY_FORM: CouponForm = {
  code: '',
  name: '',
  type: 'PERCENTAGE',
  value: '',
  min_order_value: '0',
  max_discount: '',
  end_date: '',
  usage_limit: '0',
  usage_per_customer: '1',
}

function formatValue(c: Coupon): string {
  if (c.type === 'PERCENTAGE') return `${c.value ?? 0}%`
  if (c.type === 'FIXED') return `R$ ${(c.value ?? 0).toFixed(2)}`
  return 'Frete grátis'
}

export function CouponsPage() {
  const [coupons, setCoupons] = useState<Coupon[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<CouponForm>(EMPTY_FORM)

  const fetchCoupons = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await apiClient.get('/coupons')
      setCoupons(data.coupons ?? [])
      setNotice('')
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCoupons()
  }, [fetchCoupons])

  const startCreate = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setShowForm(true)
  }

  const startEdit = (c: Coupon) => {
    setEditingId(c.id)
    setForm({
      code: c.code,
      name: c.name ?? '',
      type: c.type,
      value: c.value != null ? String(c.value) : '',
      min_order_value: String(c.min_order_value ?? 0),
      max_discount: c.max_discount != null ? String(c.max_discount) : '',
      end_date: c.end_date ? c.end_date.slice(0, 10) : '',
      usage_limit: String(c.usage_limit ?? 0),
      usage_per_customer: String(c.usage_per_customer ?? 1),
    })
    setShowForm(true)
  }

  const handleSave = async () => {
    if (!form.code.trim() || !form.end_date) {
      setNotice('Código e data final são obrigatórios.')
      return
    }
    setBusy('save')
    setNotice('')
    try {
      const payload = {
        code: form.code.trim().toUpperCase(),
        name: form.name.trim() || null,
        type: form.type,
        value: form.type === 'FREE_SHIPPING' ? null : Number(form.value) || 0,
        min_order_value: Number(form.min_order_value) || 0,
        max_discount: form.max_discount ? Number(form.max_discount) : null,
        end_date: form.end_date,
        usage_limit: Number(form.usage_limit) || 0,
        usage_per_customer: Number(form.usage_per_customer) || 1,
      }
      if (editingId) {
        await apiClient.put(`/coupons/${editingId}`, payload)
        setNotice(`Cupom "${payload.code}" atualizado.`)
      } else {
        await apiClient.post('/coupons', payload)
        setNotice(`Cupom "${payload.code}" criado.`)
      }
      setShowForm(false)
      setEditingId(null)
      fetchCoupons()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setNotice(detail || 'Falha ao salvar o cupom.')
    } finally {
      setBusy('')
    }
  }

  const handleDeactivate = async (c: Coupon) => {
    if (!confirm(`Desativar o cupom "${c.code}"?`)) return
    setBusy(c.id)
    try {
      await apiClient.delete(`/coupons/${c.id}`)
      fetchCoupons()
    } catch {
      setNotice('Falha ao desativar o cupom.')
    } finally {
      setBusy('')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return <ErrorState message="Não foi possível carregar os cupons." onRetry={fetchCoupons} />
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Promoções e Cupons</h1>
          <p className="text-sm text-muted-foreground">Cupons de desconto aplicáveis a pedidos.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchCoupons} disabled={!!busy}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={startCreate} disabled={!!busy}>
            <Plus className="mr-1 h-4 w-4" /> Novo cupom
          </Button>
        </div>
      </div>

      {notice && <div className="rounded-md bg-primary/10 p-3 text-sm text-foreground">{notice}</div>}

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>{editingId ? 'Editar cupom' : 'Novo cupom'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 md:grid-cols-3">
              <Input placeholder="Código (ex: GAS10)" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
              <Input placeholder="Nome (opcional)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <select
                className="rounded-md border border-border bg-background px-3 py-2 text-sm"
                value={form.type}
                onChange={(e) => setForm({ ...form, type: e.target.value })}
              >
                {COUPON_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              <Input
                placeholder={form.type === 'PERCENTAGE' ? 'Percentual (ex: 10)' : form.type === 'FIXED' ? 'Valor (ex: 15.90)' : '—'}
                type="number"
                value={form.value}
                disabled={form.type === 'FREE_SHIPPING'}
                onChange={(e) => setForm({ ...form, value: e.target.value })}
              />
              <Input placeholder="Pedido mínimo (R$)" type="number" value={form.min_order_value} onChange={(e) => setForm({ ...form, min_order_value: e.target.value })} />
              <Input placeholder="Desconto máximo (R$)" type="number" value={form.max_discount} onChange={(e) => setForm({ ...form, max_discount: e.target.value })} />
              <Input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} title="Data final" />
              <Input placeholder="Limite total de usos (0 = ilimitado)" type="number" value={form.usage_limit} onChange={(e) => setForm({ ...form, usage_limit: e.target.value })} />
              <Input placeholder="Usos por cliente" type="number" value={form.usage_per_customer} onChange={(e) => setForm({ ...form, usage_per_customer: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <Button onClick={handleSave} disabled={busy === 'save'}>
                <Save className="mr-1 h-4 w-4" /> Salvar
              </Button>
              <Button variant="ghost" onClick={() => { setShowForm(false); setEditingId(null) }}>
                <X className="mr-1 h-4 w-4" /> Cancelar
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {coupons.length === 0 ? (
        <EmptyState
          icon={Ticket}
          title="Nenhum cupom"
          description="Crie cupons de desconto para usar nos pedidos."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Cupons ({coupons.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4">Código</th>
                    <th className="pb-2 pr-4">Desconto</th>
                    <th className="pb-2 pr-4">Pedido mín.</th>
                    <th className="pb-2 pr-4">Validade</th>
                    <th className="pb-2 pr-4">Usos</th>
                    <th className="pb-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {coupons.map((c) => (
                    <tr key={c.id} className="border-b last:border-0">
                      <td className="py-2 pr-4">
                        <button className="font-mono font-medium hover:underline" onClick={() => startEdit(c)} title="Editar">
                          {c.code}
                        </button>
                        {c.name && <p className="text-xs text-muted-foreground">{c.name}</p>}
                      </td>
                      <td className="py-2 pr-4">{formatValue(c)}</td>
                      <td className="py-2 pr-4">{c.min_order_value > 0 ? `R$ ${c.min_order_value.toFixed(2)}` : '—'}</td>
                      <td className="py-2 pr-4">{c.end_date ? c.end_date.slice(0, 10) : '—'}</td>
                      <td className="py-2 pr-4">
                        {c.usage_count}/{c.usage_limit > 0 ? c.usage_limit : '∞'}
                      </td>
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <Badge variant={c.is_active ? 'success' : 'secondary'}>{c.is_active ? 'Ativo' : 'Inativo'}</Badge>
                          {c.is_active && (
                            <Button variant="ghost" size="icon" onClick={() => handleDeactivate(c)} disabled={busy === c.id} title="Desativar">
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
