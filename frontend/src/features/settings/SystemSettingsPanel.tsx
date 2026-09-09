import { useCallback, useEffect, useMemo, useState } from 'react'
import { SlidersHorizontal, RefreshCw, Save } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Switch } from '@/components/ui/Switch'
import { Textarea } from '@/components/ui/Textarea'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { apiClient } from '@/lib/api/client'

interface SettingRow {
  key: string
  category: string
  value: unknown
  description: string
  is_editable: boolean
  updated_by: string | null
  updated_at: string | null
}

interface SettingsResponse {
  categories: Record<string, SettingRow[]>
}

const CATEGORY_LABELS: Record<string, string> = {
  general: 'Geral',
  whatsapp: 'WhatsApp',
  notifications: 'Notificações',
  integrations: 'Integrações',
  operations: 'Operações',
  appearance: 'Aparência',
}

const CATEGORY_ORDER = ['general', 'whatsapp', 'notifications', 'integrations', 'operations', 'appearance']

/** Defaults vindos do seed do backend — preserva valor e descrição. */
const SETTING_META: Record<string, { kind: 'boolean' | 'number' | 'text' | 'textarea' | 'list' }> = {
  whatsapp_reactivate_enabled: { kind: 'boolean' },
  whatsapp_reactivate_days: { kind: 'number' },
  whatsapp_reactivate_template: { kind: 'textarea' },
  whatsapp_auto_reply: { kind: 'boolean' },
  whatsapp_agent_enabled: { kind: 'boolean' },
  notify_order_created: { kind: 'boolean' },
  notify_driver_webhook: { kind: 'text' },
  pix_enabled: { kind: 'boolean' },
  delivery_estimation_mode: { kind: 'text' },
  dark_mode: { kind: 'boolean' },
  brand_color: { kind: 'text' },
  currency: { kind: 'text' },
  timezone: { kind: 'text' },
  site_name: { kind: 'text' },
}

function inferKind(value: unknown): 'boolean' | 'number' | 'text' | 'textarea' | 'list' {
  if (typeof value === 'boolean') return 'boolean'
  if (typeof value === 'number') return 'number'
  if (Array.isArray(value)) return 'list'
  if (typeof value === 'string' && (value.includes('\n') || value.length > 80)) return 'textarea'
  return 'text'
}

export function SystemSettingsPanel() {
  const [categories, setCategories] = useState<Record<string, SettingRow[]>>({})
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [busyKey, setBusyKey] = useState('')
  const [notice, setNotice] = useState('')

  const fetchSettings = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await apiClient.get<SettingsResponse>('/settings')
      setCategories(data.categories ?? {})
      const next: Record<string, string> = {}
      for (const rows of Object.values(data.categories ?? {})) {
        for (const row of rows) {
          next[row.key] = Array.isArray(row.value)
            ? JSON.stringify(row.value)
            : row.value === null || row.value === undefined
              ? ''
              : String(row.value)
        }
      }
      setDrafts(next)
      setNotice('')
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSettings()
  }, [fetchSettings])

  const saveKey = async (row: SettingRow) => {
    setBusyKey(row.key)
    setNotice('')
    try {
      const kind = SETTING_META[row.key]?.kind ?? inferKind(row.value)
      let value: unknown = drafts[row.key]
      if (kind === 'boolean') value = String(value).toLowerCase() === 'true'
      else if (kind === 'number') value = Number(value) || 0
      else if (kind === 'list') {
        try {
          value = JSON.parse(String(value || '[]'))
        } catch {
          setNotice(`Valor inválido (JSON) em "${row.key}".`)
          return
        }
      }
      await apiClient.put(`/settings/key/${row.key}`, { value })
      setNotice(`"${row.key}" salvo.`)
      fetchSettings()
    } catch {
      setNotice(`Falha ao salvar "${row.key}".`)
    } finally {
      setBusyKey('')
    }
  }

  const sortedCategories = useMemo(() => {
    return Object.keys(categories).sort((a, b) => {
      const ia = CATEGORY_ORDER.indexOf(a)
      const ib = CATEGORY_ORDER.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })
  }, [categories])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return <ErrorState message="Não foi possível carregar as configurações do sistema." onRetry={fetchSettings} />
  }

  const total = Object.values(categories).reduce((acc, rows) => acc + rows.length, 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Configurações do Sistema</h3>
          <p className="text-sm text-muted-foreground">{total} configurações — inclui reativação de clientes via WhatsApp.</p>
        </div>
        <Button variant="outline" onClick={fetchSettings}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {notice && <div className="rounded-md bg-primary/10 p-3 text-sm text-foreground">{notice}</div>}

      {total === 0 && (
        <Card>
          <CardContent className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
            <SlidersHorizontal className="h-4 w-4" /> Nenhuma configuração disponível.
          </CardContent>
        </Card>
      )}

      {sortedCategories.map((category) => {
        const rows = categories[category] ?? []
        return (
        <Card key={category}>
          <CardHeader>
            <CardTitle>{CATEGORY_LABELS[category] ?? category}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {rows.map((row) => {
              const kind = SETTING_META[row.key]?.kind ?? inferKind(row.value)
              const dirty = drafts[row.key] !== (Array.isArray(row.value) ? JSON.stringify(row.value) : String(row.value ?? ''))
              return (
                <div key={row.key} className="space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-mono text-xs text-muted-foreground">{row.key}</p>
                      <p className="truncate text-sm">{row.description}</p>
                    </div>
                    {!row.is_editable && <Badge variant="secondary">somente leitura</Badge>}
                  </div>

                  <div className="flex items-end gap-2">
                    {kind === 'boolean' ? (
                      <div className="flex flex-1 items-center gap-2 py-1">
                        <Switch
                          checked={String(drafts[row.key]).toLowerCase() === 'true'}
                          onChange={(e) => setDrafts((d) => ({ ...d, [row.key]: String(e.target.checked) }))}
                          disabled={!row.is_editable || busyKey === row.key}
                        />
                        <span className="text-sm text-muted-foreground">{String(drafts[row.key]).toLowerCase() === 'true' ? 'Ativado' : 'Desativado'}</span>
                      </div>
                    ) : kind === 'textarea' ? (
                      <Textarea
                        className="flex-1"
                        rows={4}
                        value={drafts[row.key] ?? ''}
                        onChange={(e) => setDrafts((d) => ({ ...d, [row.key]: e.target.value }))}
                        disabled={!row.is_editable || busyKey === row.key}
                      />
                    ) : (
                      <Input
                        className="flex-1"
                        type={kind === 'number' ? 'number' : 'text'}
                        value={drafts[row.key] ?? ''}
                        onChange={(e) => setDrafts((d) => ({ ...d, [row.key]: e.target.value }))}
                        disabled={!row.is_editable || busyKey === row.key}
                      />
                    )}
                    <Button
                      size="sm"
                      onClick={() => saveKey(row)}
                      disabled={!row.is_editable || busyKey === row.key || !dirty}
                      title={dirty ? 'Salvar alteração' : 'Sem alterações'}
                    >
                      <Save className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )
            })}
          </CardContent>
        </Card>
        )
      })}
    </div>
  )
}
