import { useState, useEffect, useCallback } from 'react'
import { CreditCard, Plus, Trash2, ToggleLeft, ToggleRight, Smartphone, Edit, Save, X } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { apiClient } from '@/lib/api/client'

interface PaymentMethod {
  id: string
  code: string
  name: string
  payment_type: string
  enabled: boolean
  display_order: number
  requires_confirmation: boolean
  description: string
  fee_type: string
  fee_value: number
  discount_type: string
  discount_value: number
}

interface PixConfig {
  id: string
  key: string
  key_type: string
  holder_name: string
  holder_document: string
  institution: string
  active: boolean
}

const PAYMENT_TYPES = [
  { value: 'CASH', label: 'Dinheiro' },
  { value: 'PIX', label: 'PIX' },
  { value: 'PIX_DYNAMIC', label: 'PIX Dinâmico' },
  { value: 'DEBIT_CARD', label: 'Cartão de Débito' },
  { value: 'CREDIT_CARD', label: 'Cartão de Crédito' },
  { value: 'TRANSFER', label: 'Transferência' },
  { value: 'ON_ACCOUNT', label: 'Fiado' },
  { value: 'CUSTOM', label: 'Personalizado' },
]

const PIX_KEY_TYPES = [
  { value: 'CPF', label: 'CPF' },
  { value: 'CNPJ', label: 'CNPJ' },
  { value: 'EMAIL', label: 'E-mail' },
  { value: 'PHONE', label: 'Telefone' },
  { value: 'RANDOM', label: 'Aleatória' },
]

function PaymentMethodsTab() {
  const [methods, setMethods] = useState<PaymentMethod[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState({ code: '', name: '', payment_type: 'CASH', description: '', fee_type: 'NONE', fee_value: 0, discount_type: 'NONE', discount_value: 0 })

  const fetchMethods = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await apiClient.get('/payments/methods')
      setMethods(data.methods || [])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchMethods() }, [fetchMethods])

  const handleCreate = async () => {
    if (!form.code || !form.name) return
    try {
      await apiClient.post('/payments/methods', form)
      setShowForm(false)
      setForm({ code: '', name: '', payment_type: 'CASH', description: '', fee_type: 'NONE', fee_value: 0, discount_type: 'NONE', discount_value: 0 })
      fetchMethods()
    } catch { /* handled */ }
  }

  const handleUpdate = async () => {
    if (!editingId) return
    try {
      await apiClient.patch(`/payments/methods/${editingId}`, form)
      setEditingId(null)
      setForm({ code: '', name: '', payment_type: 'CASH', description: '', fee_type: 'NONE', fee_value: 0, discount_type: 'NONE', discount_value: 0 })
      fetchMethods()
    } catch { /* handled */ }
  }

  const handleToggle = async (id: string) => {
    try {
      await apiClient.patch(`/payments/methods/${id}/toggle`)
      fetchMethods()
    } catch { /* handled */ }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Remover este método de pagamento?')) return
    try {
      await apiClient.delete(`/payments/methods/${id}`)
      fetchMethods()
    } catch { /* handled */ }
  }

  const startEdit = (m: PaymentMethod) => {
    setEditingId(m.id)
    setForm({ code: m.code, name: m.name, payment_type: m.payment_type, description: m.description, fee_type: m.fee_type, fee_value: m.fee_value, discount_type: m.discount_type, discount_value: m.discount_value })
    setShowForm(true)
  }

  if (loading) return <div className="flex justify-center py-8"><LoadingSpinner /></div>
  if (error) return <ErrorState message="Erro ao carregar métodos de pagamento" onRetry={fetchMethods} />

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Métodos de Pagamento</h3>
        <Button onClick={() => { setShowForm(true); setEditingId(null); setForm({ code: '', name: '', payment_type: 'CASH', description: '', fee_type: 'NONE', fee_value: 0, discount_type: 'NONE', discount_value: 0 }) }}>
          <Plus className="h-4 w-4 mr-1" /> Novo
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader><CardTitle>{editingId ? 'Editar' : 'Novo'} Método</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Input placeholder="Código (ex: PIX)" value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} />
              <Input placeholder="Nome (ex: PIX)" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
              <select className="rounded-md border border-border bg-background px-3 py-2 text-sm" value={form.payment_type} onChange={e => setForm({ ...form, payment_type: e.target.value })}>
                {PAYMENT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <Input placeholder="Descrição" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <Button onClick={editingId ? handleUpdate : handleCreate}><Save className="h-4 w-4 mr-1" /> Salvar</Button>
              <Button variant="ghost" onClick={() => { setShowForm(false); setEditingId(null) }}><X className="h-4 w-4 mr-1" /> Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {methods.length === 0 ? (
        <EmptyState icon={CreditCard} title="Nenhum método configurado" description="Adicione métodos de pagamento para seus clientes." />
      ) : (
        <div className="space-y-2">
          {methods.map(m => (
            <Card key={m.id}>
              <CardContent className="flex items-center justify-between p-4">
                <div className="flex items-center gap-3">
                  <CreditCard className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium">{m.name} <span className="text-sm text-muted-foreground">({m.code})</span></p>
                    <p className="text-xs text-muted-foreground">{PAYMENT_TYPES.find(t => t.value === m.payment_type)?.label || m.payment_type}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={m.enabled ? 'success' : 'secondary'}>{m.enabled ? 'Ativo' : 'Inativo'}</Badge>
                  <Button variant="ghost" size="icon" onClick={() => handleToggle(m.id)}>
                    {m.enabled ? <ToggleRight className="h-5 w-5 text-green-500" /> : <ToggleLeft className="h-5 w-5 text-muted-foreground" />}
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => startEdit(m)}><Edit className="h-4 w-4" /></Button>
                  <Button variant="ghost" size="icon" onClick={() => handleDelete(m.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function PixConfigTab() {
  const [configs, setConfigs] = useState<PixConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ key: '', key_type: 'RANDOM', holder_name: '', holder_document: '', institution: '' })

  const fetchConfigs = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await apiClient.get('/payments/pix')
      setConfigs(data.configs || [])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchConfigs() }, [fetchConfigs])

  const handleCreate = async () => {
    if (!form.key) return
    try {
      await apiClient.post('/payments/pix', form)
      setShowForm(false)
      setForm({ key: '', key_type: 'RANDOM', holder_name: '', holder_document: '', institution: '' })
      fetchConfigs()
    } catch { /* handled */ }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Remover esta configuração PIX?')) return
    try {
      await apiClient.delete(`/payments/pix/${id}`)
      fetchConfigs()
    } catch { /* handled */ }
  }

  if (loading) return <div className="flex justify-center py-8"><LoadingSpinner /></div>
  if (error) return <ErrorState message="Erro ao carregar configuração PIX" onRetry={fetchConfigs} />

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Configuração PIX</h3>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="h-4 w-4 mr-1" /> Nova Chave
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader><CardTitle>Nova Chave PIX</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Input placeholder="Chave PIX" value={form.key} onChange={e => setForm({ ...form, key: e.target.value })} />
              <select className="rounded-md border border-border bg-background px-3 py-2 text-sm" value={form.key_type} onChange={e => setForm({ ...form, key_type: e.target.value })}>
                {PIX_KEY_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <Input placeholder="Nome do favorecido" value={form.holder_name} onChange={e => setForm({ ...form, holder_name: e.target.value })} />
              <Input placeholder="Instituição" value={form.institution} onChange={e => setForm({ ...form, institution: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreate}><Save className="h-4 w-4 mr-1" /> Salvar</Button>
              <Button variant="ghost" onClick={() => setShowForm(false)}><X className="h-4 w-4 mr-1" /> Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {configs.length === 0 ? (
        <EmptyState icon={Smartphone} title="Nenhuma chave PIX" description="Configure sua chave PIX para receber pagamentos." />
      ) : (
        <div className="space-y-2">
          {configs.map(c => (
            <Card key={c.id}>
              <CardContent className="flex items-center justify-between p-4">
                <div className="flex items-center gap-3">
                  <Smartphone className="h-5 w-5 text-green-500" />
                  <div>
                    <p className="font-medium font-mono">{c.key}</p>
                    <p className="text-xs text-muted-foreground">{PIX_KEY_TYPES.find(t => t.value === c.key_type)?.label} • {c.holder_name || 'Sem nome'} {c.institution && `• ${c.institution}`}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={c.active ? 'success' : 'secondary'}>{c.active ? 'Ativa' : 'Inativa'}</Badge>
                  <Button variant="ghost" size="icon" onClick={() => handleDelete(c.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

export function PaymentSettingsPage() {
  return (
    <Tabs defaultValue="methods">
      <TabsList>
        <TabsTrigger value="methods">Métodos de Pagamento</TabsTrigger>
        <TabsTrigger value="pix">Configuração PIX</TabsTrigger>
      </TabsList>
      <TabsContent value="methods"><PaymentMethodsTab /></TabsContent>
      <TabsContent value="pix"><PixConfigTab /></TabsContent>
    </Tabs>
  )
}
