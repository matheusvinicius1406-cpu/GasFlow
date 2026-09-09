import { useCallback, useEffect, useRef, useState } from 'react'
import { Upload, Download, RefreshCw, Sparkles, Send, Search, Users } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { apiClient } from '@/lib/api/client'

interface ContactRow {
  codigo: string
  nome: string
  telefone: string
  has_name: boolean | null
  is_whatsapp: boolean | null
  marketing_status: string | null
  endereco_definido: boolean
  last_sync_at: string | null
}

interface ContactsResponse {
  total: number
  contacts: ContactRow[]
}

export function ContactsCrmPage() {
  const [search, setSearch] = useState('')
  const [data, setData] = useState<ContactsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  const fetchContacts = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const res = await apiClient.get('/clients/contacts', {
        params: { search: search || undefined, page: 1, page_size: 100 },
      })
      setData(res.data)
      setNotice('')
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [search])

  useEffect(() => {
    fetchContacts()
  }, [fetchContacts])

  const handleImportVcf = async (file: File) => {
    setBusy('import')
    setNotice('')
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await apiClient.post('/clients/contacts/import-vcf', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setNotice(`Importação: ${res.data.created} criados, ${res.data.updated} atualizados.`)
      fetchContacts()
    } catch {
      setNotice('Falha ao importar o arquivo .vcf.')
    } finally {
      setBusy('')
    }
  }

  const handleExport = async () => {
    setBusy('export')
    try {
      const res = await apiClient.get('/clients/contacts/export-vcf', { responseType: 'blob' })
      const url = URL.createObjectURL(res.data as Blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'gasflow-contatos.vcf'
      link.click()
      URL.revokeObjectURL(url)
    } catch {
      setNotice('Falha ao exportar contatos.')
    } finally {
      setBusy('')
    }
  }

  const handleSync = async () => {
    setBusy('sync')
    try {
      // 1) Sync local do serviço WhatsApp (SQLite) — já dispara o push ao CRM.
      // 2) Reforço: chama o crm-sync direto (idempotente, upsert por telefone).
      //    O push real ao backend usa X-GasFlow-Key (service-to-service) —
      //    o frontend nunca chama /sync-batch diretamente.
      await apiClient.post('/whatsapp/contacts/sync')
      await apiClient.post('/whatsapp/crm-sync').catch(() => null)
      setNotice('Sincronização disparada — contatos chegam ao CRM em instantes.')
      fetchContacts()
    } catch {
      setNotice('Falha ao sincronizar (WhatsApp conectado?).')
    } finally {
      setBusy('')
    }
  }

  const handleReactivate = async (dryRun: boolean) => {
    setBusy(dryRun ? 'preview' : 'reactivate')
    try {
      const res = await apiClient.post('/clients/contacts/reactivate', { dry_run: dryRun, limit: 50 })
      if (dryRun) {
        setNotice(
          `Reativação: ${res.data.total_eligible} elegíveis (inativos há ${res.data.days} dias). Nada enviado.`,
        )
      } else {
        setNotice(`Reativação: ${res.data.created} mensagens na fila (envio pelo executor de automações).`)
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setNotice(detail || 'Falha na reativação (habilitada em Configurações › Sistema?).')
    } finally {
      setBusy('')
    }
  }

  const contacts = data?.contacts ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Contatos</h1>
          <p className="text-sm text-muted-foreground">
            Clientes do CRM sincronizados com o WhatsApp — importe, exporte e reative.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={!!busy}>
            <Upload className="mr-1 h-4 w-4" /> {busy === 'import' ? 'Importando...' : 'Importar .vcf'}
          </Button>
          <Button variant="outline" onClick={handleExport} disabled={!!busy}>
            <Download className="mr-1 h-4 w-4" /> Exportar .vcf
          </Button>
          <Button variant="outline" onClick={handleSync} disabled={!!busy}>
            <RefreshCw className="mr-1 h-4 w-4" /> Sincronizar WhatsApp
          </Button>
        </div>
      </div>

      <input
        ref={fileInput}
        type="file"
        accept=".vcf,text/vcard"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) handleImportVcf(file)
          e.target.value = ''
        }}
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-64 flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Buscar por nome, telefone ou código..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button variant="ghost" onClick={() => handleReactivate(true)} disabled={!!busy}>
          <Sparkles className="mr-1 h-4 w-4" /> {busy === 'preview' ? 'Analisando...' : 'Pré-visualizar reativação'}
        </Button>
        <Button onClick={() => handleReactivate(false)} disabled={!!busy}>
          <Send className="mr-1 h-4 w-4" /> {busy === 'reactivate' ? 'Enfileirando...' : 'Reativar inativos'}
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
        <ErrorState message="Não foi possível carregar os contatos." onRetry={fetchContacts} />
      ) : contacts.length === 0 ? (
        <EmptyState
          icon={Users}
          title="Nenhum contato"
          description="Importe um .vcf, sincronize com o WhatsApp ou crie clientes no CRM."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Contatos ({data?.total ?? contacts.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4">Código</th>
                    <th className="pb-2 pr-4">Nome</th>
                    <th className="pb-2 pr-4">Telefone</th>
                    <th className="pb-2 pr-4">Endereço</th>
                    <th className="pb-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {contacts.map((c) => (
                    <tr key={c.codigo} className="border-b last:border-0">
                      <td className="py-2 pr-4 font-mono text-xs">{c.codigo}</td>
                      <td className="py-2 pr-4">{c.nome}</td>
                      <td className="py-2 pr-4 font-mono text-xs">{c.telefone}</td>
                      <td className="py-2 pr-4">
                        {c.endereco_definido ? (
                          '✓'
                        ) : (
                          <Badge variant="secondary">a definir</Badge>
                        )}
                      </td>
                      <td className="py-2">
                        <Badge
                          variant={
                            c.marketing_status === 'OPTED_OUT' || c.marketing_status === 'BLOCKED'
                              ? 'destructive'
                              : 'default'
                          }
                        >
                          {c.marketing_status || 'UNKNOWN'}
                        </Badge>
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
