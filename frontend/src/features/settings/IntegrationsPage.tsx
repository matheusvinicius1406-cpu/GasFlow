import { useCallback, useEffect, useState } from 'react'
import { Plug, Plus, RefreshCw, Trash2, KeyRound, Wifi, Copy } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { apiClient } from '@/lib/api/client'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/features/auth'

/**
 * Integrações — conexão de sites de revenda ao GasFlow.
 *
 * A feature existia inteira no backend (`/integrations`: criar, editar, testar,
 * sincronizar, rotacionar token e excluir) e **não tinha nenhuma tela**: o
 * endpoint de exclusão era inalcançável porque não havia nem lista para
 * excluir de dentro. Esta página é essa superfície.
 *
 * Duas semânticas que a tela precisa deixar explícitas, porque não são óbvias:
 * - **Excluir é soft delete** (`DELETE /integrations/{id}` marca
 *   `is_active=false`): o histórico de sincronização fica preservado e não há
 *   caminho de reativação — a integração desativada continua listada, marcada.
 * - **O token de importação aparece uma vez** quando é rotacionado; depois só
 *   é possível vê-lo pela coluna (ele fica gravado na integração).
 */
interface Integration {
  id: string
  name: string
  description: string | null
  base_url: string
  orders_path: string | null
  auth_type: string
  has_credentials: boolean
  import_token: string | null
  sync_interval_minutes: number
  is_active: boolean
  last_sync_at: string | null
  last_sync_status: string | null
}

const AUTH_LABELS: Record<string, string> = {
  none: 'Nenhuma',
  basic: 'Usuário e senha',
  token: 'Token',
  cookie: 'Cookie',
}

const SYNC_STATUS_VARIANTS: Record<string, 'success' | 'destructive' | 'warning' | 'secondary'> = {
  SUCCESS: 'success',
  OK: 'success',
  ERROR: 'destructive',
  FAILED: 'destructive',
  PARTIAL: 'warning',
}

const EMPTY_FORM = {
  name: '',
  base_url: '',
  orders_path: '',
  auth_type: 'none',
  sync_interval_minutes: '5',
}

export function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [freshToken, setFreshToken] = useState<{ id: string; token: string } | null>(null)
  const { success, error: toastError, info } = useToast()
  const { hasPermission } = useAuth()
  const canWrite = hasPermission('integration.write')

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const res = await apiClient.get('/integrations')
      setIntegrations(res.data.integrations || [])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  async function handleCreate() {
    if (!form.name.trim() || !form.base_url.trim()) return
    setSaving(true)
    try {
      await apiClient.post('/integrations', {
        name: form.name.trim(),
        base_url: form.base_url.trim(),
        ...(form.orders_path.trim() ? { orders_path: form.orders_path.trim() } : {}),
        auth_type: form.auth_type,
        sync_interval_minutes: Number(form.sync_interval_minutes) || 5,
      })
      setFormOpen(false)
      setForm({ ...EMPTY_FORM })
      success('Integração criada', 'Gere o token de importação para o agente da revenda.')
      await fetchData()
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 403) toastError('Sem permissão', 'Seu usuário não pode criar integrações.')
      else if (status === 400) toastError('Dados inválidos', 'Confira a URL base e o nome.')
      else toastError('Erro ao criar', 'Nada foi salvo. Tente novamente.')
    } finally {
      setSaving(false)
    }
  }

  async function handleRotateToken(integration: Integration) {
    const confirmed = window.confirm(
      `Rotacionar o token de importação de ${integration.name}?\n\n` +
      'O token atual para de funcionar imediatamente — o agente da revenda precisa ser atualizado com o novo.',
    )
    if (!confirmed) return

    setBusy(`token-${integration.id}`)
    try {
      const res = await apiClient.post(`/integrations/${integration.id}/rotate-token`)
      setFreshToken({ id: integration.id, token: res.data.import_token })
      success('Token rotacionado', 'Copie o novo token agora e atualize o agente.')
      await fetchData()
    } catch (err) {
      reportError(err, 'rotacionar o token', fetchData)
    } finally {
      setBusy(null)
    }
  }

  async function handleTest(integration: Integration) {
    setBusy(`test-${integration.id}`)
    try {
      await apiClient.post(`/integrations/${integration.id}/test-connection`)
      success('Conexão bem-sucedida', integration.base_url)
    } catch (err) {
      reportError(err, 'testar a conexão', fetchData)
    } finally {
      setBusy(null)
    }
  }

  async function handleSync(integration: Integration) {
    setBusy(`sync-${integration.id}`)
    try {
      await apiClient.post(`/integrations/${integration.id}/sync`)
      success('Sincronização iniciada', integration.name)
      await fetchData()
    } catch (err) {
      reportError(err, 'sincronizar', fetchData)
    } finally {
      setBusy(null)
    }
  }

  /**
   * Excluir = soft delete. A integração sai de circulação (`is_active=false`),
   * mas o histórico de sincronização fica e não há reativação — por isso a
   * confirmação diz o que realmente acontece, e a lista continua mostrando a
   * linha marcada como desativada em vez de sumir com ela.
   */
  async function handleDelete(integration: Integration) {
    const confirmed = window.confirm(
      `Excluir a integração ${integration.name}?\n\n` +
      'Ela é DESATIVADA (soft delete): para de sincronizar e o token de importação deixa de valer. ' +
      'O histórico de sincronização é preservado. Não há como reativar pela tela.',
    )
    if (!confirmed) return

    setBusy(`delete-${integration.id}`)
    try {
      await apiClient.delete(`/integrations/${integration.id}`)
      success('Integração desativada', `${integration.name} — histórico preservado.`)
      await fetchData()
    } catch (err) {
      reportError(err, 'excluir', fetchData)
    } finally {
      setBusy(null)
    }
  }

  /** Mensagem específica por status; recarrega a lista quando ela está velha (404). */
  function reportError(err: unknown, action: string, reload: () => Promise<void>) {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 404) {
      toastError('Integração não encontrada', 'Pode já ter sido removida — a lista foi recarregada.')
      void reload()
      return
    }
    if (status === 409) {
      toastError('Ação bloqueada', `Uma regra de negócio impede ${action} — nada foi alterado.`)
      return
    }
    if (status === 403) {
      toastError('Sem permissão', `Seu usuário não pode ${action} integrações.`)
      return
    }
    toastError(`Erro ao ${action}`, 'Nada foi alterado. Tente novamente.')
  }

  async function copyToken(token: string) {
    try {
      await navigator.clipboard.writeText(token)
      info('Token copiado', 'Cole no agente da revenda.')
    } catch {
      toastError('Não foi possível copiar', 'Selecione o token e copie manualmente.')
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
    return (
      <ErrorState
        message="Não foi possível carregar as integrações."
        onRetry={() => fetchData()}
      />
    )
  }

  return (
    <Page>
      <PageHeader>
        <PageTitle subtitle="Sites de revenda conectados ao GasFlow">
          Integrações
        </PageTitle>
        <PageActions>
          {canWrite && (
            <Button onClick={() => setFormOpen(!formOpen)}>
              <Plus className="h-4 w-4 mr-1" /> Nova integração
            </Button>
          )}
        </PageActions>
      </PageHeader>

      {freshToken && (
        <Card>
          <CardContent className="p-4 space-y-2">
            <p className="text-sm font-medium">Token de importação — aparece uma vez</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-md border border-border bg-muted px-3 py-2 text-xs break-all">
                {freshToken.token}
              </code>
              <Button variant="outline" size="sm" onClick={() => copyToken(freshToken.token)}>
                <Copy className="h-4 w-4 mr-1" /> Copiar
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setFreshToken(null)}>Fechar</Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Atualize o agente da revenda com este token; o anterior deixou de funcionar.
            </p>
          </CardContent>
        </Card>
      )}

      {formOpen && (
        <Card>
          <CardHeader><CardTitle>Nova integração</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input
              aria-label="Nome da integração"
              placeholder="Nome (ex.: Revenda Centro)"
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
            />
            <Input
              aria-label="URL base da integração"
              placeholder="URL base (ex.: https://revenda.com.br)"
              value={form.base_url}
              onChange={e => setForm({ ...form, base_url: e.target.value })}
            />
            <Input
              aria-label="Caminho dos pedidos"
              placeholder="Caminho dos pedidos (opcional, ex.: /api/pedidos)"
              value={form.orders_path}
              onChange={e => setForm({ ...form, orders_path: e.target.value })}
            />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <select
                aria-label="Tipo de autenticação"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                value={form.auth_type}
                onChange={e => setForm({ ...form, auth_type: e.target.value })}
              >
                {Object.entries(AUTH_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <Input
                aria-label="Intervalo de sincronização em minutos"
                type="number"
                min={1}
                max={1440}
                value={form.sync_interval_minutes}
                onChange={e => setForm({ ...form, sync_interval_minutes: e.target.value })}
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreate} disabled={saving || !form.name.trim() || !form.base_url.trim()}>
                {saving ? 'Salvando...' : 'Criar'}
              </Button>
              <Button variant="ghost" onClick={() => setFormOpen(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {integrations.length === 0 ? (
        <EmptyState
          icon={Plug}
          title="Nenhuma integração"
          description="Conecte o site de uma revenda para importar pedidos automaticamente."
          action={canWrite ? <Button onClick={() => setFormOpen(true)}><Plus className="h-4 w-4" /> Nova integração</Button> : undefined}
        />
      ) : (
        <Card>
          <CardHeader><CardTitle>Integrações</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Integração</TableHead>
                  <TableHead>URL base</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Última sincronização</TableHead>
                  <TableHead>Token</TableHead>
                  <TableHead>Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {integrations.map(integration => (
                  <TableRow key={integration.id}>
                    <TableCell>
                      <div className="font-medium">{integration.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {AUTH_LABELS[integration.auth_type] || integration.auth_type}
                        {integration.description ? ` • ${integration.description}` : ''}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs font-mono break-all">{integration.base_url}</TableCell>
                    <TableCell>
                      <Badge variant={integration.is_active ? 'success' : 'secondary'}>
                        {integration.is_active ? 'Ativa' : 'Desativada'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {integration.last_sync_at
                        ? new Date(integration.last_sync_at).toLocaleString('pt-BR')
                        : 'Nunca'}
                      {integration.last_sync_status && (
                        <Badge
                          className="ml-2"
                          variant={SYNC_STATUS_VARIANTS[integration.last_sync_status] || 'secondary'}
                        >
                          {integration.last_sync_status}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-xs font-mono">
                      {integration.import_token ? `${integration.import_token.slice(0, 10)}…` : '—'}
                    </TableCell>
                    <TableCell>
                      {integration.is_active && canWrite && (
                        <div className="flex flex-wrap items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleTest(integration)}
                            disabled={busy === `test-${integration.id}`}
                            aria-label={`Testar conexão com ${integration.name}`}
                          >
                            <Wifi className="h-4 w-4 mr-1" />
                            {busy === `test-${integration.id}` ? 'Testando...' : 'Testar'}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleSync(integration)}
                            disabled={busy === `sync-${integration.id}`}
                            aria-label={`Sincronizar ${integration.name} agora`}
                          >
                            <RefreshCw className="h-4 w-4 mr-1" />
                            {busy === `sync-${integration.id}` ? 'Sincronizando...' : 'Sincronizar'}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRotateToken(integration)}
                            disabled={busy === `token-${integration.id}`}
                            aria-label={`Rotacionar token de ${integration.name}`}
                          >
                            <KeyRound className="h-4 w-4 mr-1" />
                            {busy === `token-${integration.id}` ? 'Gerando...' : 'Novo token'}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDelete(integration)}
                            disabled={busy === `delete-${integration.id}`}
                            aria-label={`Excluir ${integration.name}`}
                            className="text-destructive hover:bg-destructive/10 focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <Trash2 className="h-4 w-4 mr-1" />
                            {busy === `delete-${integration.id}` ? 'Excluindo...' : 'Excluir'}
                          </Button>
                        </div>
                      )}
                      {!integration.is_active && (
                        <span className="text-xs text-muted-foreground">
                          Desativada — sem ações. O histórico de sincronização fica.
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </Page>
  )
}
