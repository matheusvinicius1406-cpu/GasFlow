/**
 * Segments Page — CRM customer segmentation management.
 *
 * Features:
 * - List segments with status and member count
 * - Create/edit segments with rules
 * - Preview segment members
 * - Evaluate segments
 * - Delete segments
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Users, Plus, Search, RefreshCw, Trash2, Edit, Eye, Play,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { apiClient } from '@/lib/api/client'

// ── Types ────────────────────────────────────────────────

interface SegmentRule {
  field: string
  operator: string
  value: string | number | boolean | null
}

interface Segment {
  id: number
  name: string
  description: string
  rules: SegmentRule[]
  rule_logic: string
  status: string
  member_count: number
  last_evaluated_at: string | null
  created_at: string | null
  updated_at: string | null
}

interface RuleField {
  value: string
  label: string
  type: string
}

interface PreviewMember {
  codigo: string
  metrics: Record<string, unknown>
}

// ── Constants ────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' | 'info' }> = {
  DRAFT: { label: 'Rascunho', variant: 'secondary' },
  ACTIVE: { label: 'Ativo', variant: 'success' },
  ARCHIVED: { label: 'Arquivado', variant: 'destructive' },
}

const DEFAULT_STATUS = { label: 'Desconhecido', variant: 'secondary' as const }



const OPERATOR_LABELS: Record<string, string> = {
  equals: 'Igual a',
  not_equals: 'Diferente de',
  greater_than: 'Maior que',
  less_than: 'Menor que',
  greater_or_equal: 'Maior ou igual',
  less_or_equal: 'Menor ou igual',
  contains: 'Contém',
  not_contains: 'Não contém',
  is_true: 'É verdadeiro',
  is_false: 'É falso',
}

// ── Rule Editor ──────────────────────────────────────────

function RuleEditor({
  rule,
  onChange,
  onRemove,
  fields,
}: {
  rule: SegmentRule
  onChange: (rule: SegmentRule) => void
  onRemove: () => void
  fields: RuleField[]
}) {
  const field = fields.find(f => f.value === rule.field)
  const isBoolean = field?.type === 'boolean'
  const isString = field?.type === 'string'

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <select
        value={rule.field}
        onChange={(e) => onChange({ ...rule, field: e.target.value, value: null })}
        className="rounded-md border border-input bg-background px-3 py-2 text-sm"
      >
        {fields.map(f => (
          <option key={f.value} value={f.value}>{f.label}</option>
        ))}
      </select>

      {!isBoolean && (
        <select
          value={rule.operator}
          onChange={(e) => onChange({ ...rule, operator: e.target.value })}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm"
        >
          {Object.entries(OPERATOR_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      )}

      {isBoolean ? (
        <select
          value={String(rule.value ?? true)}
          onChange={(e) => onChange({ ...rule, value: e.target.value === 'true' })}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm"
        >
          <option value="true">Sim</option>
          <option value="false">Não</option>
        </select>
      ) : !isString || ['equals', 'not_equals', 'contains', 'not_contains'].includes(rule.operator) ? (
        <Input
          type={field?.type === 'number' ? 'number' : 'text'}
          value={rule.value?.toString() ?? ''}
          onChange={(e) => onChange({
            ...rule,
            value: field?.type === 'number' ? parseFloat(e.target.value) || 0 : e.target.value,
          })}
          placeholder="Valor"
          className="w-32"
        />
      ) : null}

      <Button onClick={onRemove} variant="ghost" size="icon" className="text-destructive">
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  )
}

// ── Segment Form ─────────────────────────────────────────

function SegmentForm({
  segment,
  onSave,
  onCancel,
  loading,
}: {
  segment?: Segment | null
  onSave: (data: { name: string; description: string; rules: SegmentRule[]; rule_logic: string }) => void
  onCancel: () => void
  loading: boolean
}) {
  const [name, setName] = useState(segment?.name ?? '')
  const [description, setDescription] = useState(segment?.description ?? '')
  const [rules, setRules] = useState<SegmentRule[]>(segment?.rules ?? [])
  const [ruleLogic, setRuleLogic] = useState(segment?.rule_logic ?? 'AND')
  const [fields, setFields] = useState<RuleField[]>([])

  useEffect(() => {
    apiClient.get('/segments/rules').then(({ data }) => {
      setFields(data.fields || [])
    }).catch(() => {})
  }, [])

  const addRule = () => {
    setRules([...rules, { field: 'total_orders', operator: 'greater_than', value: 0 }])
  }

  const updateRule = (index: number, rule: SegmentRule) => {
    const newRules = [...rules]
    newRules[index] = rule
    setRules(newRules)
  }

  const removeRule = (index: number) => {
    setRules(rules.filter((_, i) => i !== index))
  }

  const handleSubmit = () => {
    if (!name.trim()) return
    onSave({ name: name.trim(), description: description.trim(), rules, rule_logic: ruleLogic })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{segment ? 'Editar Segmento' : 'Novo Segmento'}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Nome *</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex: Clientes VIP" />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Lógica</label>
            <select
              value={ruleLogic}
              onChange={(e) => setRuleLogic(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
            >
              <option value="AND">Todas as regras (AND)</option>
              <option value="OR">Qualquer regra (OR)</option>
            </select>
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">Descrição</label>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Descreva o segmento" />
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-foreground">Regras ({rules.length})</label>
            <Button onClick={addRule} variant="outline" size="sm">
              <Plus className="h-4 w-4 mr-1" /> Adicionar Regra
            </Button>
          </div>

          {rules.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Nenhuma regra definida. Adicione regras para segmentar clientes.
            </p>
          ) : (
            <div className="space-y-2">
              {rules.map((rule, i) => (
                <div key={i} className="flex items-center gap-2 p-2 rounded-lg border border-border">
                  <span className="text-xs text-muted-foreground w-6">{i + 1}.</span>
                  <RuleEditor
                    rule={rule}
                    onChange={(r) => updateRule(i, r)}
                    onRemove={() => removeRule(i)}
                    fields={fields}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>Cancelar</Button>
          <Button onClick={handleSubmit} disabled={loading || !name.trim()}>
            {loading ? 'Salvando...' : 'Salvar'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Preview Panel ────────────────────────────────────────

function PreviewPanel({ segmentId, onClose }: { segmentId: number; onClose: () => void }) {
  const [preview, setPreview] = useState<{ total_evaluated: number; total_matches: number; members: PreviewMember[] } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiClient.post(`/segments/${segmentId}/preview`)
      .then(({ data }) => setPreview(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [segmentId])

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Preview do Segmento</CardTitle>
          <Button onClick={onClose} variant="ghost" size="sm">Fechar</Button>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <LoadingSpinner />
        ) : preview ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-lg bg-muted p-3 text-center">
                <p className="text-2xl font-bold">{preview.total_evaluated}</p>
                <p className="text-xs text-muted-foreground">Avaliados</p>
              </div>
              <div className="rounded-lg bg-primary/10 p-3 text-center">
                <p className="text-2xl font-bold text-primary">{preview.total_matches}</p>
                <p className="text-xs text-muted-foreground">Correspondem</p>
              </div>
            </div>

            {preview.members.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Código</TableHead>
                    <TableHead>Pedidos</TableHead>
                    <TableHead>Total Gasto</TableHead>
                    <TableHead>Último Pedido</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.members.map((m) => (
                    <TableRow key={m.codigo}>
                      <TableCell className="font-mono">{m.codigo}</TableCell>
                      <TableCell>{String(m.metrics.total_orders)}</TableCell>
                      <TableCell>R$ {Number(m.metrics.total_spent).toFixed(2)}</TableCell>
                      <TableCell>{m.metrics.days_since_last_order != null ? `${m.metrics.days_since_last_order}d` : '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

// ── Main Page ────────────────────────────────────────────

export function SegmentsPage() {
  const [segments, setSegments] = useState<Segment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [editingSegment, setEditingSegment] = useState<Segment | null>(null)
  const [previewId, setPreviewId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')

  const fetchSegments = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await apiClient.get('/segments')
      setSegments(data || [])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchSegments() }, [fetchSegments])

  const handleSave = async (data: { name: string; description: string; rules: SegmentRule[]; rule_logic: string }) => {
    setSaving(true)
    try {
      if (editingSegment) {
        await apiClient.put(`/segments/${editingSegment.id}`, data)
      } else {
        await apiClient.post('/segments', data)
      }
      setShowForm(false)
      setEditingSegment(null)
      fetchSegments()
    } catch {
      // error handled silently
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Excluir este segmento?')) return
    try {
      await apiClient.delete(`/segments/${id}`)
      fetchSegments()
    } catch {
      // silent
    }
  }

  const handleEvaluate = async (id: number) => {
    try {
      await apiClient.post(`/segments/${id}/evaluate`)
      fetchSegments()
    } catch {
      // silent
    }
  }

  const filtered = segments.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.description.toLowerCase().includes(search.toLowerCase())
  )

  if (loading) {
    return <div className="flex items-center justify-center py-16"><LoadingSpinner size="lg" /></div>
  }

  if (error) {
    return <ErrorState message="Não foi possível carregar os segmentos." onRetry={fetchSegments} />
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Segmentação de Clientes</h1>
          <p className="text-sm text-muted-foreground">
            Crie regras para segmentar seus clientes automaticamente.
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={fetchSegments} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => { setShowForm(true); setEditingSegment(null) }}>
            <Plus className="h-4 w-4 mr-1" /> Novo Segmento
          </Button>
        </div>
      </div>

      {showForm && (
        <SegmentForm
          segment={editingSegment}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditingSegment(null) }}
          loading={saving}
        />
      )}

      {previewId && (
        <PreviewPanel segmentId={previewId} onClose={() => setPreviewId(null)} />
      )}

      {segments.length === 0 && !showForm ? (
        <EmptyState
          icon={Users}
          title="Nenhum segmento criado"
          description="Crie segmentos para agrupar clientes por regras como: total gasto, frequência de compra, tipo de cliente, etc."
          action={
            <Button onClick={() => setShowForm(true)}>
              <Plus className="h-4 w-4 mr-1" /> Criar Primeiro Segmento
            </Button>
          }
        />
      ) : (
        <>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Buscar segmentos..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10 max-w-md"
            />
          </div>

          <div className="space-y-3">
            {filtered.map((segment) => {
              const statusConfig = STATUS_CONFIG[segment.status] ?? DEFAULT_STATUS
              return (
                <Card key={segment.id}>
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-foreground">{segment.name}</h3>
                          <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
                          <span className="text-sm text-muted-foreground">
                            {segment.member_count} cliente{segment.member_count !== 1 ? 's' : ''}
                          </span>
                        </div>
                        {segment.description && (
                          <p className="text-sm text-muted-foreground">{segment.description}</p>
                        )}
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span>{segment.rules.length} regra{segment.rules.length !== 1 ? 's' : ''}</span>
                          <span>•</span>
                          <span>Lógica: {segment.rule_logic}</span>
                          {segment.last_evaluated_at && (
                            <>
                              <span>•</span>
                              <span>Avaliado: {new Date(segment.last_evaluated_at).toLocaleDateString('pt-BR')}</span>
                            </>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-1">
                        <Button
                          onClick={() => handleEvaluate(segment.id)}
                          variant="ghost"
                          size="sm"
                          title="Avaliar"
                        >
                          <Play className="h-4 w-4" />
                        </Button>
                        <Button
                          onClick={() => setPreviewId(previewId === segment.id ? null : segment.id)}
                          variant="ghost"
                          size="sm"
                          title="Preview"
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          onClick={() => { setEditingSegment(segment); setShowForm(true) }}
                          variant="ghost"
                          size="sm"
                          title="Editar"
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          onClick={() => handleDelete(segment.id)}
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          title="Excluir"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
