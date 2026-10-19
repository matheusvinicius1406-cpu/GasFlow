import { useCallback, useEffect, useState } from 'react'
import { ListChecks, RefreshCw, Plus, Trash2, Users, UserRound, Sprout } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'
import { apiClient } from '@/lib/api/client'

interface ListRow {
  id: number
  name: string
  description: string | null
  contactCount: number
  customerCount: number
}

interface ListsResponse {
  total: number
  lists: ListRow[]
}

interface ListContact {
  id: number
  name: string | null
  push_name: string | null
  phone: string | null
  is_business: number | null
}

interface ListContactsResponse {
  total: number
  contacts: ListContact[]
}

interface ListCustomer {
  id: number
  contact_id: number
  customer_status: string
  contact: {
    phone: string | null
    name: string | null
    push_name: string | null
  }
}

interface ListCustomersResponse {
  total: number
  customers: ListCustomer[]
}

type Tab = 'contacts' | 'customers'

export function ListsPage() {
  const [lists, setLists] = useState<ListRow[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [tab, setTab] = useState<Tab>('contacts')
  const [contacts, setContacts] = useState<ListContactsResponse | null>(null)
  const [customers, setCustomers] = useState<ListCustomersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [newContactId, setNewContactId] = useState('')
  const [newCustomerId, setNewCustomerId] = useState('')

  const fetchLists = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiClient.get<ListsResponse>('/whatsapp/lists')
      setLists(res.data.lists ?? [])
      setNotice('')
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchMembers = useCallback(async (listId: number) => {
    const [c, cu] = await Promise.all([
      apiClient.get(`/whatsapp/lists/${listId}/contacts`).catch(() => null),
      apiClient.get(`/whatsapp/lists/${listId}/customers`).catch(() => null),
    ])
    setContacts(c ? c.data : null)
    setCustomers(cu ? cu.data : null)
  }, [])

  useEffect(() => {
    fetchLists()
  }, [fetchLists])

  useEffect(() => {
    if (selectedId != null) fetchMembers(selectedId)
  }, [selectedId, fetchMembers])

  const fail = (err: unknown, fallback: string) => {
    const detail = (err as { response?: { data?: { error?: string; detail?: string } } })?.response?.data
    setNotice(detail?.detail || detail?.error || fallback)
  }

  const handleSync = async () => {
    if (selectedId == null) return
    setBusy('sync')
    setNotice('')
    try {
      const res = await apiClient.post(`/whatsapp/lists/${selectedId}/sync`)
      setNotice(
        `Lista sincronizada: ${res.data.contactCount} contato(s) e ${res.data.customerCount} cliente(s).`,
      )
      await fetchLists()
      await fetchMembers(selectedId)
    } catch (err) {
      fail(err, 'Falha ao sincronizar a lista.')
    } finally {
      setBusy('')
    }
  }

  const handleSeed = async () => {
    setBusy('seed')
    setNotice('')
    try {
      const res = await apiClient.post('/whatsapp/lists/seed')
      const created = Array.isArray(res.data.results)
        ? res.data.results.filter((r: { created?: boolean }) => r.created).length
        : 0
      setNotice(`Semeadura: ${created} lista(s) criada(s) a partir das regras.`)
      await fetchLists()
    } catch {
      setNotice('Falha ao semear as listas.')
    } finally {
      setBusy('')
    }
  }

  const handleAddContact = async () => {
    if (selectedId == null || !newContactId.trim()) return
    setBusy('add-contact')
    setNotice('')
    try {
      await apiClient.post(`/whatsapp/lists/${selectedId}/contacts/${newContactId.trim()}`)
      setNotice(`Contato ${newContactId.trim()} adicionado à lista.`)
      setNewContactId('')
      await fetchMembers(selectedId)
    } catch (err) {
      fail(err, 'Falha ao adicionar o contato.')
    } finally {
      setBusy('')
    }
  }

  const handleRemoveContact = async (contactId: number) => {
    if (selectedId == null) return
    setBusy(`rm-contact-${contactId}`)
    setNotice('')
    try {
      await apiClient.delete(`/whatsapp/lists/${selectedId}/contacts/${contactId}`)
      await fetchMembers(selectedId)
    } catch (err) {
      fail(err, 'Falha ao remover o contato.')
    } finally {
      setBusy('')
    }
  }

  const handleAddCustomer = async () => {
    if (selectedId == null || !newCustomerId.trim()) return
    setBusy('add-customer')
    setNotice('')
    try {
      await apiClient.post(`/whatsapp/lists/${selectedId}/customers/${newCustomerId.trim()}`)
      setNotice(`Cliente ${newCustomerId.trim()} adicionado à lista.`)
      setNewCustomerId('')
      await fetchMembers(selectedId)
    } catch (err) {
      fail(err, 'Falha ao adicionar o cliente.')
    } finally {
      setBusy('')
    }
  }

  const handleRemoveCustomer = async (customerId: number) => {
    if (selectedId == null) return
    setBusy(`rm-customer-${customerId}`)
    setNotice('')
    try {
      await apiClient.delete(`/whatsapp/lists/${selectedId}/customers/${customerId}`)
      await fetchMembers(selectedId)
    } catch (err) {
      fail(err, 'Falha ao remover o cliente.')
    } finally {
      setBusy('')
    }
  }

  const selected = lists.find((l) => l.id === selectedId) ?? null
  const contactRows = contacts?.contacts ?? []
  const customerRows = customers?.customers ?? []

  return (
    <Page>
      <PageHeader>
        <PageTitle subtitle="Listas de disparo — gerencie quem entra em cada campanha.">
          Listas
        </PageTitle>
        <PageActions>
          <Button variant="outline" onClick={handleSeed} disabled={!!busy}>
            <Sprout className="mr-1 h-4 w-4" /> {busy === 'seed' ? 'Semeando...' : 'Semear listas'}
          </Button>
        </PageActions>
      </PageHeader>

      {notice && (
        <div className="rounded-md bg-primary/10 p-3 text-sm text-foreground">{notice}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <LoadingSpinner size="lg" />
        </div>
      ) : error ? (
        <ErrorState message="Não foi possível carregar as listas." error={error} onRetry={fetchLists} />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Listas ({lists.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {lists.length === 0 ? (
                <EmptyState
                  icon={ListChecks}
                  title="Nenhuma lista"
                  description="Use 'Semear listas' para criar as listas padrão a partir das regras."
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="pb-2 pr-4">ID</th>
                        <th className="pb-2 pr-4">Nome</th>
                        <th className="pb-2 pr-4">Contatos</th>
                        <th className="pb-2">Clientes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lists.map((l) => (
                        <tr
                          key={l.id}
                          className={`border-b last:border-0 ${l.id === selectedId ? 'bg-primary/5' : ''}`}
                        >
                          <td className="py-2 pr-4 font-mono text-xs">{l.id}</td>
                          <td className="py-2 pr-4">
                            <Button
                              variant={l.id === selectedId ? 'default' : 'ghost'}
                              size="sm"
                              onClick={() => setSelectedId(l.id)}
                            >
                              {l.name}
                            </Button>
                          </td>
                          <td className="py-2 pr-4">
                            <Badge variant="secondary">{l.contactCount}</Badge>
                          </td>
                          <td className="py-2">
                            <Badge variant="secondary">{l.customerCount}</Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {selected && (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle>{selected.name}</CardTitle>
                  <div className="flex items-center gap-2">
                    <Button
                      variant={tab === 'contacts' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setTab('contacts')}
                    >
                      <Users className="mr-1 h-4 w-4" /> Contatos ({contacts?.total ?? 0})
                    </Button>
                    <Button
                      variant={tab === 'customers' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setTab('customers')}
                    >
                      <UserRound className="mr-1 h-4 w-4" /> Clientes ({customers?.total ?? 0})
                    </Button>
                    <Button size="sm" onClick={handleSync} disabled={!!busy}>
                      <RefreshCw className="mr-1 h-4 w-4" />
                      {busy === 'sync' ? 'Sincronizando...' : 'Sincronizar'}
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {tab === 'contacts' ? (
                  <>
                    <div className="flex flex-wrap items-center gap-2">
                      <Input
                        aria-label="ID do contato a adicionar"
                        placeholder="ID do contato"
                        value={newContactId}
                        onChange={(e) => setNewContactId(e.target.value)}
                        className="w-40"
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleAddContact}
                        disabled={!!busy || !newContactId.trim()}
                      >
                        <Plus className="mr-1 h-4 w-4" /> Adicionar contato
                      </Button>
                    </div>
                    {contactRows.length === 0 ? (
                      <EmptyState
                        icon={Users}
                        title="Lista vazia"
                        description="Adicione um contato pelo ID ou sincronize a lista."
                      />
                    ) : (
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-muted-foreground">
                            <th className="pb-2 pr-4">ID</th>
                            <th className="pb-2 pr-4">Nome</th>
                            <th className="pb-2 pr-4">Telefone</th>
                            <th className="pb-2">Ação</th>
                          </tr>
                        </thead>
                        <tbody>
                          {contactRows.map((c) => (
                            <tr key={c.id} className="border-b last:border-0">
                              <td className="py-2 pr-4 font-mono text-xs">{c.id}</td>
                              <td className="py-2 pr-4">{c.name || c.push_name || '—'}</td>
                              <td className="py-2 pr-4 font-mono text-xs">{c.phone || '—'}</td>
                              <td className="py-2">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleRemoveContact(c.id)}
                                  disabled={!!busy}
                                  aria-label={`Remover contato ${c.id}`}
                                >
                                  <Trash2 className="mr-1 h-4 w-4" />
                                  {busy === `rm-contact-${c.id}` ? 'Removendo...' : 'Remover'}
                                </Button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </>
                ) : (
                  <>
                    <div className="flex flex-wrap items-center gap-2">
                      <Input
                        aria-label="ID do cliente a adicionar"
                        placeholder="ID do cliente"
                        value={newCustomerId}
                        onChange={(e) => setNewCustomerId(e.target.value)}
                        className="w-40"
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleAddCustomer}
                        disabled={!!busy || !newCustomerId.trim()}
                      >
                        <Plus className="mr-1 h-4 w-4" /> Adicionar cliente
                      </Button>
                    </div>
                    {customerRows.length === 0 ? (
                      <EmptyState
                        icon={UserRound}
                        title="Nenhum cliente"
                        description="Adicione um cliente pelo ID ou sincronize a lista."
                      />
                    ) : (
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-muted-foreground">
                            <th className="pb-2 pr-4">ID</th>
                            <th className="pb-2 pr-4">Nome</th>
                            <th className="pb-2 pr-4">Telefone</th>
                            <th className="pb-2 pr-4">Status</th>
                            <th className="pb-2">Ação</th>
                          </tr>
                        </thead>
                        <tbody>
                          {customerRows.map((c) => (
                            <tr key={c.id} className="border-b last:border-0">
                              <td className="py-2 pr-4 font-mono text-xs">{c.id}</td>
                              <td className="py-2 pr-4">
                                {c.contact?.name || c.contact?.push_name || '—'}
                              </td>
                              <td className="py-2 pr-4 font-mono text-xs">
                                {c.contact?.phone || '—'}
                              </td>
                              <td className="py-2 pr-4">
                                <Badge variant={c.customer_status === 'CUSTOMER' ? 'default' : 'secondary'}>
                                  {c.customer_status || 'UNKNOWN'}
                                </Badge>
                              </td>
                              <td className="py-2">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleRemoveCustomer(c.id)}
                                  disabled={!!busy}
                                  aria-label={`Remover cliente ${c.id}`}
                                >
                                  <Trash2 className="mr-1 h-4 w-4" />
                                  {busy === `rm-customer-${c.id}` ? 'Removendo...' : 'Remover'}
                                </Button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </Page>
  )
}
