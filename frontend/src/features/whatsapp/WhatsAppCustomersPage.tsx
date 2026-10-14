import { useCallback, useEffect, useState } from 'react'
import { UserRound, RefreshCw, ShieldCheck, ShieldOff, ArrowUpRight } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'
import { apiClient } from '@/lib/api/client'

const STATUSES = ['CUSTOMER', 'PROSPECT', 'UNKNOWN']

interface CustomerRow {
  id: number
  contact_id: number
  customer_status: string
  /** LGPD — vem do LEFT JOIN em contact_preferences (sem preferência = UNKNOWN). */
  marketing_status: string
  contact: {
    phone: string | null
    name: string | null
    push_name: string | null
    business_name: string | null
  }
}

interface CustomersResponse {
  total: number
  customers: CustomerRow[]
}

interface NodeContact {
  id: number
  phone: string | null
  name: string | null
  push_name: string | null
  business_name: string | null
}

export function WhatsAppCustomersPage() {
  const [data, setData] = useState<CustomersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [promoteContactId, setPromoteContactId] = useState('')
  const [nodeContacts, setNodeContacts] = useState<NodeContact[]>([])

  const fetchCustomers = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const res = await apiClient.get('/whatsapp/customers', {
        params: { limit: 200, offset: 0 },
      })
      setData(res.data)
      setNotice('')
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCustomers()
  }, [fetchCustomers])

  // Contatos do Node (ids do Node) — alimenta o seletor de promote.
  // Não bloqueia a tela: se falhar, o promote fica indisponível.
  useEffect(() => {
    apiClient
      .get('/whatsapp/node-contacts', { params: { limit: 200, offset: 0 } })
      .then((res) => setNodeContacts(res.data.contacts ?? []))
      .catch(() => setNodeContacts([]))
  }, [])

  const fail = (err: unknown, fallback: string) => {
    const detail = (err as { response?: { data?: { error?: string; detail?: string } } })?.response?.data
    setNotice(detail?.detail || detail?.error || fallback)
  }

  const handleSync = async () => {
    setBusy('sync')
    setNotice('')
    try {
      await apiClient.post('/whatsapp/customers/sync')
      setNotice('Sincronização de clientes disparada.')
      await fetchCustomers()
    } catch {
      setNotice('Falha ao sincronizar os clientes.')
    } finally {
      setBusy('')
    }
  }

  const handleStatus = async (customerId: number, status: string) => {
    setBusy(`status-${customerId}`)
    setNotice('')
    try {
      await apiClient.put(`/whatsapp/customers/${customerId}/status`, { status })
      setNotice(`Cliente ${customerId} agora é ${status}.`)
      await fetchCustomers()
    } catch (err) {
      fail(err, 'Falha ao alterar o status.')
    } finally {
      setBusy('')
    }
  }

  const handleOpt = async (customerId: number, action: 'opt-in' | 'opt-out') => {
    setBusy(`${action}-${customerId}`)
    setNotice('')
    try {
      // Literais separados: o gate de integridade extrai o caminho do template
      // literal, e um `${action}` dinâmico viraria `*/*` e não casaria com a rota.
      if (action === 'opt-in') {
        await apiClient.post(`/whatsapp/customers/${customerId}/opt-in`)
      } else {
        await apiClient.post(`/whatsapp/customers/${customerId}/opt-out`)
      }
      setNotice(`Cliente ${customerId}: ${action === 'opt-in' ? 'opt-in registrado' : 'opt-out registrado'}.`)
      await fetchCustomers()
    } catch (err) {
      fail(err, 'Falha ao registrar a preferência.')
    } finally {
      setBusy('')
    }
  }

  const handlePromote = async () => {
    const id = promoteContactId.trim()
    if (!id) return
    setBusy('promote')
    setNotice('')
    try {
      await apiClient.post(`/whatsapp/customers/${id}/promote`, { status: 'UNKNOWN' })
      setNotice(`Contato ${id} promovido a cliente.`)
      setPromoteContactId('')
      await fetchCustomers()
    } catch (err) {
      fail(err, 'Falha ao promover o contato.')
    } finally {
      setBusy('')
    }
  }

  const customers = data?.customers ?? []

  return (
    <Page>
      <PageHeader>
        <PageTitle subtitle="Base de envio do WhatsApp — consentimento LGPD e status de marketing. Não é o cadastro do CRM.">
          Base WhatsApp
        </PageTitle>
        <PageActions>
          <Button variant="outline" onClick={handleSync} disabled={!!busy}>
            <RefreshCw className="mr-1 h-4 w-4" /> {busy === 'sync' ? 'Sincronizando...' : 'Sincronizar'}
          </Button>
        </PageActions>
      </PageHeader>

      <div className="flex flex-wrap items-center gap-2 rounded-md border p-3">
        <span className="text-sm text-muted-foreground">Promover contato a cliente:</span>
        <select
          aria-label="Contato a promover a cliente"
          className="h-9 rounded-md border bg-transparent px-2 text-sm"
          value={promoteContactId}
          onChange={(e) => setPromoteContactId(e.target.value)}
          disabled={!!busy || nodeContacts.length === 0}
        >
          <option value="">
            {nodeContacts.length === 0
              ? 'Nenhum contato disponível'
              : `Escolher entre ${nodeContacts.length} contatos...`}
          </option>
          {nodeContacts.map((c) => (
            <option key={c.id} value={String(c.id)}>
              {c.business_name || c.name || c.push_name || c.phone || `#${c.id}`} — #{c.id}
            </option>
          ))}
        </select>
        <Button
          variant="outline"
          size="sm"
          onClick={handlePromote}
          disabled={!!busy || !promoteContactId.trim()}
        >
          <ArrowUpRight className="mr-1 h-4 w-4" />
          {busy === 'promote' ? 'Promovendo...' : 'Promover'}
        </Button>
      </div>

      {notice && (
        <div className="rounded-md bg-primary/10 p-3 text-sm text-foreground">{notice}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <LoadingSpinner size="lg" />
        </div>
      ) : error ? (
        <ErrorState message="Não foi possível carregar os clientes." onRetry={fetchCustomers} />
      ) : customers.length === 0 ? (
        <EmptyState
          icon={UserRound}
          title="Nenhum cliente"
          description="Promova contatos a clientes na tela de Contatos ou sincronize o WhatsApp."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Clientes ({data?.total ?? customers.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4">ID</th>
                    <th className="pb-2 pr-4">Nome</th>
                    <th className="pb-2 pr-4">Telefone</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">Consentimento</th>
                    <th className="pb-2">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {customers.map((c) => (
                    <tr key={c.id} className="border-b last:border-0">
                      <td className="py-2 pr-4 font-mono text-xs">{c.id}</td>
                      <td className="py-2 pr-4">
                        {c.contact?.business_name || c.contact?.name || c.contact?.push_name || '—'}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs">{c.contact?.phone || '—'}</td>
                      <td className="py-2 pr-4">
                        <Badge variant={c.customer_status === 'CUSTOMER' ? 'default' : 'secondary'}>
                          {c.customer_status || 'UNKNOWN'}
                        </Badge>
                      </td>
                      <td className="py-2 pr-4">
                        <Badge
                          variant={
                            c.marketing_status === 'OPTED_IN'
                              ? 'default'
                              : c.marketing_status === 'OPTED_OUT' || c.marketing_status === 'SUPPRESSED'
                                ? 'destructive'
                                : 'secondary'
                          }
                        >
                          {c.marketing_status || 'UNKNOWN'}
                        </Badge>
                        <div className="mt-1 flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpt(c.id, 'opt-in')}
                            disabled={!!busy || c.marketing_status === 'OPTED_IN'}
                            aria-label={`Registrar opt-in do cliente ${c.id}`}
                          >
                            <ShieldCheck className="mr-1 h-4 w-4" />
                            {busy === `opt-in-${c.id}` ? '...' : 'Opt-in'}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpt(c.id, 'opt-out')}
                            disabled={!!busy || c.marketing_status === 'OPTED_OUT'}
                            aria-label={`Registrar opt-out do cliente ${c.id}`}
                          >
                            <ShieldOff className="mr-1 h-4 w-4" />
                            {busy === `opt-out-${c.id}` ? '...' : 'Opt-out'}
                          </Button>
                        </div>
                      </td>
                      <td className="py-2">
                        <select
                          aria-label={`Status do cliente ${c.id}`}
                          className="h-8 rounded-md border bg-transparent px-2 text-xs"
                          value={STATUSES.includes(c.customer_status) ? c.customer_status : 'UNKNOWN'}
                          disabled={!!busy}
                          onChange={(e) => handleStatus(c.id, e.target.value)}
                        >
                          {STATUSES.map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </Page>
  )
}
