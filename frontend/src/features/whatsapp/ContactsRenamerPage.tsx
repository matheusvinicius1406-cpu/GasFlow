import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Download,
  ListChecks,
  Loader2,
  MapPin,
  Play,
  Route,
  Search,
  XCircle,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'
import { apiClient } from '@/lib/api/client'

/**
 * Renomeador de contatos (.vcf) — Fase 2 §9 etapa 8.
 *
 * Fecha o fluxo em lote da tela:
 *   prévia PAGINADA (nada grava) → job bounded-batch (progresso) → triagem →
 *   export .vcf já no nome de rota.
 *
 * O backend é bounded-batch: cada `process` é curto, então a tela chama até o
 * job concluir. A flag `CONTACT_RENAMER_ENABLED` desligada devolve 409 — a tela
 * mostra o motivo em vez de falhar em silêncio.
 */

type JobTipo = 'GEOCODE' | 'OVERPASS' | 'APPLY'

interface RenameChange {
  codigo: string
  telefone: string
  before: string
  after: string
  bairro: string
}

interface PreviewResponse {
  changes: RenameChange[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface ConflictItem {
  codigo: string
  nome: string
  telefone: string
  issues: string[]
}

interface ConflictsResponse {
  total: number
  items: ConflictItem[]
}

interface RuasCepItem {
  rua: string
  bairro: string
  cidade: string
  uf: string
  cep: string
  provider: string
}

/** Origem do geocode (etapa 9): OSM × fallback de CEP (BrasilAPI/PontoFato). */
interface GeocodeOrigemResponse {
  por_status: Record<string, number>
  por_origem: { osm: number; cep: number }
  total_ruas_cache: number
  total_ruas_cep: number
  ruas_cep: RuasCepItem[]
}

interface JobResponse {
  id: string
  tipo: JobTipo
  status: 'PENDENTE' | 'PROCESSANDO' | 'CONCLUIDO' | 'FALHOU'
  total: number
  processados: number
  alterados: number
  restantes: number
  metrica: Record<string, number>
  erro: string | null
}

const PAGE_SIZE = 25
const JOB_TIPOS: { tipo: JobTipo; label: string; hint: string }[] = [
  { tipo: 'GEOCODE', label: 'Geocodificar', hint: 'Resolve a rua de cada contato pendente.' },
  { tipo: 'OVERPASS', label: 'Entre ruas', hint: 'Preenche o "entre A e B" das ruas já resolvidas.' },
  { tipo: 'APPLY', label: 'Renomear', hint: 'Grava o nome de rota nos contatos (respeita as regras).' },
]

const ISSUE_LABELS: Record<string, string> = {
  duplicate_name: 'Nome duplicado',
  bad_phone: 'Telefone inválido',
}

// Quem respondeu pelo CEP. O ponto é de *trecho*, não da casa (ADR-0007).
const PROVIDER_LABELS: Record<string, string> = {
  brasilapi: 'BrasilAPI',
  pontofato: 'PontoFato',
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function errorDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return detail || fallback
}

export function ContactsRenamerPage() {
  // ── Regra (espelha RenameRule do backend) ──
  const [patternEndereco, setPatternEndereco] = useState(true)
  const [patternBairro, setPatternBairro] = useState(false)
  const [stripPrefixes, setStripPrefixes] = useState(true)
  const [caseMode, setCaseMode] = useState<'title' | 'upper' | 'lower' | ''>('')

  // ── Filtros (viram query da prévia e filtro do job) ──
  const [search, setSearch] = useState('')
  const [bairro, setBairro] = useState('')
  const [status, setStatus] = useState('')

  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [conflicts, setConflicts] = useState<ConflictsResponse | null>(null)
  const [origem, setOrigem] = useState<GeocodeOrigemResponse | null>(null)
  const [job, setJob] = useState<JobResponse | null>(null)
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState(false)
  const cancelRef = useRef(false)

  const buildRule = useCallback(
    () => ({
      trim: true,
      strip_prefixes: stripPrefixes,
      case: caseMode || null,
      pattern_bairro: patternBairro,
      pattern_endereco: patternEndereco,
    }),
    [stripPrefixes, caseMode, patternBairro, patternEndereco],
  )

  const fetchConflicts = useCallback(async () => {
    try {
      const res = await apiClient.get('/whatsapp/contacts/organizer/conflicts')
      setConflicts(res.data)
    } catch {
      /* triagem é secundária — falha não bloqueia a página */
    }
  }, [])

  /** Origem do geocode (OSM × CEP) — alimenta a triagem do fallback. */
  const fetchOrigem = useCallback(async () => {
    try {
      const res = await apiClient.get('/whatsapp/contacts/organizer/geocode-origem')
      setOrigem(res.data)
    } catch {
      /* triagem é secundária — falha não bloqueia a página */
    }
  }, [])

  useEffect(() => {
    fetchConflicts()
    fetchOrigem()
    return () => {
      cancelRef.current = true
    }
  }, [fetchConflicts, fetchOrigem])

  const fetchPreview = useCallback(
    async (targetPage: number) => {
      setBusy('preview')
      setError(false)
      setNotice('')
      try {
        const res = await apiClient.post('/whatsapp/contacts/organizer/rename-preview', buildRule(), {
          params: {
            page: targetPage,
            page_size: PAGE_SIZE,
            search: search || undefined,
            bairro: bairro || undefined,
            status: status || undefined,
          },
        })
        setPreview(res.data)
        setPage(res.data.page)
      } catch {
        setError(true)
      } finally {
        setBusy('')
      }
    },
    [buildRule, search, bairro, status],
  )

  /** Chama `process` até concluir; cada request fica curto (bounded-batch). */
  const runJob = useCallback(async (created: JobResponse) => {
    let atual = created
    setJob(atual)
    cancelRef.current = false
    while (!cancelRef.current && atual.status !== 'CONCLUIDO' && atual.status !== 'FALHOU') {
      const res = await apiClient.post(`/whatsapp/contacts/jobs/${atual.id}/process`)
      atual = res.data
      setJob(atual)
      if (atual.status !== 'CONCLUIDO' && atual.status !== 'FALHOU') await sleep(400)
    }
    return atual
  }, [])

  const startJob = async (tipo: JobTipo) => {
    setBusy(`job-${tipo}`)
    setNotice('')
    setJob(null)
    try {
      const filtro = { search: search || undefined, bairro: bairro || undefined, status: status || undefined }
      const res = await apiClient.post('/whatsapp/contacts/jobs', {
        tipo,
        filtro,
        regra: tipo === 'APPLY' ? buildRule() : undefined,
      })
      const fim = await runJob(res.data as JobResponse)
      setNotice(
        `Job ${tipo} ${fim.status.toLowerCase()}: ${fim.processados} processado(s), ${fim.alterados} alterado(s).`,
      )
      if (tipo === 'APPLY') fetchConflicts()
    } catch (err) {
      setNotice(errorDetail(err, `Falha ao rodar o job ${tipo}.`))
    } finally {
      setBusy('')
    }
  }

  const stopJob = () => {
    cancelRef.current = true
    setNotice('Parada solicitada — o job continua de onde parou na próxima execução.')
  }

  const exportVcf = async () => {
    setBusy('export')
    try {
      const res = await apiClient.get('/whatsapp/contacts/export-vcf', {
        params: { formatar_rota: true },
        responseType: 'blob',
      })
      const url = URL.createObjectURL(res.data as Blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'gasflow-contatos-renomeado.vcf'
      link.click()
      URL.revokeObjectURL(url)
    } catch {
      setNotice('Falha ao exportar o .vcf.')
    } finally {
      setBusy('')
    }
  }

  const progresso = job && job.total > 0 ? Math.min(100, Math.round((job.processados / job.total) * 100)) : 0
  const jobRodando = busy.startsWith('job-')

  return (
    <Page>
      <PageHeader>
        <PageTitle subtitle="Renomeie a agenda em lote para o padrão de rota — confira antes de aplicar.">
          Renomeador de Contatos
        </PageTitle>
        <PageActions>
          <Button variant="outline" onClick={exportVcf} disabled={busy === 'export'}>
            <Download className="mr-1 h-4 w-4" /> Exportar .vcf renomeado
          </Button>
        </PageActions>
      </PageHeader>

      {notice && (
        <div className="rounded-md bg-primary/10 p-3 text-sm text-foreground" role="status">
          {notice}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ── Regras + filtros ── */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Regras e filtros</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={patternEndereco} onChange={(e) => setPatternEndereco(e.target.checked)} />
              Padrão de rota <code className="text-xs">1= rua Nº 10 - CEP ... (Nome)</code>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={patternBairro} onChange={(e) => setPatternBairro(e.target.checked)} />
              Padrão &quot;Nome — Bairro&quot;
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={stripPrefixes} onChange={(e) => setStripPrefixes(e.target.checked)} />
              Remover prefixos (WA-, WPP-, +…)
            </label>
            <div className="flex items-center gap-2 text-sm">
              <span>Capitalização:</span>
              <select
                className="rounded-md border px-2 py-1 text-sm"
                value={caseMode}
                onChange={(e) => setCaseMode(e.target.value as typeof caseMode)}
                aria-label="Capitalização"
              >
                <option value="">Manter</option>
                <option value="title">Title Case</option>
                <option value="upper">MAIÚSCULAS</option>
                <option value="lower">minúsculas</option>
              </select>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <Input
                  aria-label="Buscar contatos"
                  placeholder="Buscar por nome, telefone…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                />
              </div>
              <Input
                aria-label="Filtrar por bairro"
                placeholder="Bairro (exato)"
                value={bairro}
                onChange={(e) => setBairro(e.target.value)}
              />
              <select
                className="rounded-md border px-2 py-1 text-sm"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                aria-label="Filtrar por situação do endereço"
              >
                <option value="">Toda situação</option>
                <option value="PENDENTE">Pendente</option>
                <option value="NAO_ENCONTRADO">Não encontrado</option>
                <option value="OK">Resolvido</option>
                <option value="SEM_ENDERECO">Sem endereço</option>
              </select>
            </div>

            <Button onClick={() => fetchPreview(1)} disabled={busy === 'preview'}>
              {busy === 'preview' ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <ListChecks className="mr-1 h-4 w-4" />}
              Gerar prévia
            </Button>
          </CardContent>
        </Card>

        {/* ── Progresso do job ── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Route className="h-4 w-4" /> Processamento em lote
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {JOB_TIPOS.map(({ tipo, label, hint }) => (
                <Button
                  key={tipo}
                  variant={tipo === 'APPLY' ? 'default' : 'outline'}
                  onClick={() => startJob(tipo)}
                  disabled={jobRodando}
                  title={hint}
                >
                  {busy === `job-${tipo}` ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Play className="mr-1 h-4 w-4" />}
                  {label}
                </Button>
              ))}
              {jobRodando && (
                <Button variant="ghost" onClick={stopJob}>
                  <XCircle className="mr-1 h-4 w-4" /> Parar
                </Button>
              )}
            </div>

            {job && (
              <div className="space-y-2" data-testid="job-progress">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{job.tipo}</span>
                  <Badge variant={job.status === 'CONCLUIDO' ? 'default' : 'secondary'}>{job.status}</Badge>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div className="h-full bg-primary transition-all" style={{ width: `${progresso}%` }} />
                </div>
                <p className="text-xs text-muted-foreground">
                  {job.processados}/{job.total} processado(s) · {job.alterados} alterado(s)
                  {job.erro ? ` · erro: ${job.erro}` : ''}
                </p>
                {job.tipo === 'OVERPASS' && job.metrica && (
                  <p className="text-xs text-muted-foreground" data-testid="overpass-metrica">
                    ruas: {job.metrica.ruas ?? 0} · com 2+ âncoras:{' '}
                    {job.metrica.ruas_com_2_ancoras ?? 0} · com "entre": {job.metrica.ruas_com_intersecoes ?? 0}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Triagem (Revisar) ── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            Triagem
            {conflicts && conflicts.total > 0 && <Badge variant="destructive">{conflicts.total}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!conflicts ? (
            <LoadingSpinner />
          ) : conflicts.total === 0 ? (
            <EmptyState icon={ListChecks} title="Sem pendências" description="Nenhum conflito de nome ou telefone." />
          ) : (
            <ul className="max-h-64 space-y-2 overflow-y-auto text-sm" data-testid="triage-list">
              {conflicts.items.map((item) => (
                <li key={item.codigo} className="rounded-md border px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{item.nome}</span>
                    <span className="flex gap-1">
                      {item.issues.map((issue) => (
                        <Badge key={issue} variant="secondary">
                          {ISSUE_LABELS[issue] ?? issue}
                        </Badge>
                      ))}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {item.codigo} · {item.telefone}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ── Origem do geocode (etapa 9: OSM × fallback de CEP) ── */}
      {origem?.por_origem && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <MapPin className="h-4 w-4" /> Origem do endereço
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3" data-testid="origem-geocode">
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary" data-testid="origem-osm">
                OSM: {origem.por_origem.osm} rua(s)
              </Badge>
              <Badge
                variant={origem.por_origem.cep > 0 ? 'warning' : 'secondary'}
                data-testid="origem-cep"
              >
                CEP (fallback): {origem.por_origem.cep} rua(s)
              </Badge>
              {typeof origem.por_status?.PENDENTE === 'number' && (
                <Badge variant="outline">Pendentes: {origem.por_status.PENDENTE}</Badge>
              )}
              {typeof origem.por_status?.NAO_ENCONTRADO === 'number' && (
                <Badge variant="outline">Não encontrados: {origem.por_status.NAO_ENCONTRADO}</Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              O CEP é coordenada de trecho, não da casa: confira as ruas resolvidas pelo fallback antes de
              aplicar.
            </p>
            {origem.ruas_cep?.length > 0 && (
              <ul className="max-h-48 space-y-1 overflow-y-auto" data-testid="origem-cep-lista">
                {origem.ruas_cep.map((r) => (
                  <li
                    key={`${r.rua}-${r.provider}`}
                    className="flex items-center justify-between gap-2 rounded-md border px-2 py-1 text-xs"
                  >
                    <span className="truncate">{`${r.rua}${r.bairro ? ` — ${r.bairro}` : ''}`}</span>
                    <Badge variant="outline">{PROVIDER_LABELS[r.provider] ?? r.provider}</Badge>
                  </li>
                ))}
              </ul>
            )}
            {origem.total_ruas_cep > (origem.ruas_cep?.length ?? 0) && (
              <p className="text-xs text-muted-foreground">
                Mostrando {origem.ruas_cep?.length ?? 0} de {origem.total_ruas_cep} rua(s) via CEP.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Prévia paginada ── */}
      {error && <ErrorState message="Não foi possível gerar a prévia." onRetry={() => fetchPreview(page)} />}

      {preview && !error && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <MapPin className="h-4 w-4" />
              Prévia — {preview.total} mudança(s)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {preview.total === 0 ? (
              <EmptyState
                icon={ListChecks}
                title="Nada a mudar"
                description="Nenhum contato seria alterado com essas regras e filtros."
              />
            ) : (
              <>
                <div className="max-h-96 overflow-auto rounded-md border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-left">
                      <tr>
                        <th className="p-2">Antes</th>
                        <th className="p-2">Depois</th>
                        <th className="p-2">Código</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.changes.map((c) => (
                        <tr key={c.codigo} className="border-t">
                          <td className="p-2 text-muted-foreground line-through">{c.before}</td>
                          <td className="p-2 font-medium">{c.after}</td>
                          <td className="p-2 font-mono text-xs">{c.codigo}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">
                    Página {preview.page} de {preview.total_pages}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => fetchPreview(preview.page - 1)}
                      disabled={preview.page <= 1 || busy === 'preview'}
                      aria-label="Página anterior"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => fetchPreview(preview.page + 1)}
                      disabled={preview.page >= preview.total_pages || busy === 'preview'}
                      aria-label="Próxima página"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </Page>
  )
}
