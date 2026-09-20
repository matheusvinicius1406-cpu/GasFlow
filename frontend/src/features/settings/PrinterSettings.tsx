import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Printer,
  RefreshCw,
  RotateCcw,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Alert } from '@/components/ui/Alert'
import { Select } from '@/components/ui/Select'
import { EmptyState } from '@/components/ui/EmptyState'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { useToast } from '@/components/ui/Toast'
import { apiClient } from '@/lib/api/client'
import { formatDateTime } from '@/lib/utils'

/** Job sem data (nunca reivindicado) não pode virar "01/01/1970". */
function when(value: string | null): string {
  return value ? formatDateTime(value) : '—'
}

/**
 * Impressora — F10.7/F10.8.
 *
 * Duas metades, de propósito:
 *   - LOCAL (ponte Electron `window.gasflow`): impressoras instaladas no
 *     Windows, escolha, estado do worker e teste de impressão. Só existe
 *     dentro do app.
 *   - BACKEND (API), que funciona também no navegador: a fila é do servidor,
 *     então a lista/reenvio de jobs é útil de qualquer lugar.
 *
 * O operador precisa entender onde está o problema: o cupom ficou na fila
 * (backend) ou a térmica recusou (máquina). Por isso o estado local e a fila
 * aparecem juntos, com o motivo real do erro em vez de "falha ao imprimir".
 */

interface InstalledPrinter {
  name: string
  displayName: string
  isDefault: boolean
}

interface LocalPrinterStatus {
  running: boolean
  printerName: string
  state: 'ONLINE' | 'OFFLINE' | 'ERROR' | 'NOT_CONFIGURED'
  printed: number
  /** Cupons que NÃO saíram de novo (job devolvido à fila pelo backend). */
  replayed: number
  failed: number
  lastTickAt: number | null
  lastError: string
}

interface PrinterBridge {
  printerList?: () => Promise<{ ok: boolean; printers: InstalledPrinter[]; error?: string }>
  printerSetName?: (name: string) => Promise<{ ok: boolean; printerName: string }>
  printerStatus?: () => Promise<{ ok: boolean; status: LocalPrinterStatus }>
  printerTest?: () => Promise<{ ok: boolean; error?: string; printerName?: string }>
}

interface BackendPrinterStatus {
  status: string
  printer_name: string | null
  detail: string
  /** ISO do relato do agente (o backend manda string; aqui já foi number). */
  reported_at: string | null
  /** Último relato é velho demais (ou não existe): o app pode estar fechado. */
  stale: boolean
  pending_jobs: number
  failed_jobs: number
  /** Cupons de dia anterior que NÃO saem sozinhos (precisam de reimpressão). */
  expired_jobs: number
  total_jobs_today: number
}

interface PrintJob {
  id: string
  order_id: string
  status: string
  is_reprint: boolean
  attempts: number
  error: string | null
  created_at: string | null
  completed_at: string | null
}

/** A ponte só existe dentro do Electron (contextIsolation) — no navegador, não. */
function printerBridge(): PrinterBridge | undefined {
  return (window as { gasflow?: PrinterBridge }).gasflow
}

const STATE_LABEL: Record<string, { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' }> = {
  ONLINE: { label: 'Pronta', variant: 'success' },
  OFFLINE: { label: 'Offline', variant: 'warning' },
  ERROR: { label: 'Com erro', variant: 'destructive' },
  NOT_CONFIGURED: { label: 'Não configurada', variant: 'secondary' },
}

const JOB_LABEL: Record<string, { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' | 'info' }> = {
  PENDING: { label: 'Na fila', variant: 'info' },
  PROCESSING: { label: 'Imprimindo', variant: 'warning' },
  COMPLETED: { label: 'Impresso', variant: 'success' },
  FAILED: { label: 'Falhou', variant: 'destructive' },
  // Ficou na fila desde outro dia: não sai sozinho (evita pilha de cupom velho).
  EXPIRED: { label: 'Vencido', variant: 'warning' },
}

export function PrinterSettings() {
  const toast = useToast()
  const bridge = printerBridge()

  const [printers, setPrinters] = useState<InstalledPrinter[]>([])
  const [selected, setSelected] = useState('')
  const [local, setLocal] = useState<LocalPrinterStatus | null>(null)
  const [backend, setBackend] = useState<BackendPrinterStatus | null>(null)
  const [jobs, setJobs] = useState<PrintJob[]>([])
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const [retrying, setRetrying] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    // O backend é a fonte da fila; o estado local vem da ponte. Nenhum dos
    // dois pode derrubar a tela: cada um falha em separado.
    const [statusRes, jobsRes] = await Promise.allSettled([
      apiClient.get<BackendPrinterStatus>('/printer/status'),
      apiClient.get<{ jobs: PrintJob[] }>('/printer/jobs', { params: { limit: 25 } }),
    ])

    if (statusRes.status === 'fulfilled') setBackend(statusRes.value.data)
    if (jobsRes.status === 'fulfilled') setJobs(jobsRes.value.data.jobs ?? [])

    if (bridge?.printerStatus) {
      try {
        const res = await bridge.printerStatus()
        if (res?.ok) {
          setLocal(res.status)
          setSelected((prev) => prev || res.status.printerName || '')
        }
      } catch {
        /* ponte indisponível: a metade local simplesmente não aparece */
      }
    }

    if (bridge?.printerList) {
      try {
        const res = await bridge.printerList()
        if (res?.ok) setPrinters(res.printers)
      } catch {
        /* idem */
      }
    }
    setLoading(false)
  }, [bridge])

  useEffect(() => {
    void refresh()
    // A fila muda enquanto o operador olha (o agente consome a cada 3s).
    const timer = setInterval(() => void refresh(), 5000)
    return () => clearInterval(timer)
  }, [refresh])

  const choosePrinter = async (name: string) => {
    setSelected(name)
    if (!bridge?.printerSetName) return
    try {
      const res = await bridge.printerSetName(name)
      if (res?.ok) {
        toast.success('Impressora definida', name || 'Nenhuma impressora selecionada')
        await refresh()
      }
    } catch {
      toast.error('Não foi possível salvar a impressora', 'Tente novamente.')
    }
  }

  const testPrint = async () => {
    if (!bridge?.printerTest) return
    setTesting(true)
    try {
      const res = await bridge.printerTest()
      if (res?.ok) {
        toast.success('Cupom de teste enviado', `Impressora: ${res.printerName}`)
      } else {
        toast.error('A impressora recusou o teste', res?.error || 'Sem detalhes do spooler.')
      }
    } catch (e) {
      toast.error('Falha no teste de impressão', e instanceof Error ? e.message : 'Erro inesperado.')
    } finally {
      setTesting(false)
      await refresh()
    }
  }

  const retryJob = async (job: PrintJob) => {
    setRetrying(job.id)
    try {
      const { data } = await apiClient.post(`/printer/jobs/${job.id}/retry`)
      const isNew = data?.job?.is_reprint
      toast.success(
        isNew ? 'Reimpressão na fila' : 'Job reenfileirado',
        `Pedido #${job.order_id}`
      )
      await refresh()
    } catch {
      toast.error('Não foi possível reenviar', `Pedido #${job.order_id}`)
    } finally {
      setRetrying(null)
    }
  }

  const state = local ? STATE_LABEL[local.state] ?? STATE_LABEL.OFFLINE : null
  const configured = (local?.printerName || selected || '').trim().length > 0
  // Vencido conta como atenção: o cupom não saiu e depende do operador.
  const needingAttention =
    (backend?.pending_jobs ?? 0) + (backend?.failed_jobs ?? 0) + (backend?.expired_jobs ?? 0)
  /**
   * O agente não reporta há mais de 30s: com 2 workers isso também acontecia
   * quando o estado vivia na memória de um deles. A tela precisa avisar em vez
   * de mostrar "Pronta" olhando um estado velho.
   */
  const stale = backend?.stale === true

  return (
    <div className="space-y-4">
      {!bridge && (
        <Alert variant="info" title="Configuração da impressora só no aplicativo">
          Este navegador não tem acesso ao spooler do Windows. Escolher a impressora e testar
          funciona no <strong>app GasFlow Desktop</strong>; a fila abaixo é do servidor e pode ser
          acompanhada de qualquer lugar.
        </Alert>
      )}

      {bridge && !configured && (
        <Alert variant="warning" title="Nenhuma impressora escolhida">
          Os pedidos pagos ficam na fila até uma impressora ser escolhida — nada é perdido.
          Selecione a térmica abaixo e use <strong>Testar impressão</strong> para confirmar.
        </Alert>
      )}

      {stale && (
        <Alert variant="warning" title="Sem sinal do app de impressão">
          O aplicativo parou de reportar (último sinal: {when(backend?.reported_at ?? null)}).{' '}
          {needingAttention > 0
            ? `${needingAttention} cupom(ns) esperando na fila — nada foi perdido, eles saem quando o app voltar.`
            : 'Nenhum cupom esperando agora.'}
        </Alert>
      )}

      {(backend?.expired_jobs ?? 0) > 0 && (
        <Alert variant="info" title="Cupons de dia anterior não saíram">
          {backend?.expired_jobs} cupom(ns) ficaram na fila desde outro dia e não são impressos
          automaticamente — cupom de pedido já entregue só gasta papel. Use{' '}
          <strong>Reimprimir</strong> na lista abaixo se algum ainda for necessário.
        </Alert>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="flex items-center gap-2">
              <Printer className="h-5 w-5" />
              Impressora térmica
            </CardTitle>
            <div className="flex items-center gap-2">
              {state && <Badge variant={state.variant}>{state.label}</Badge>}
              <Button variant="outline" size="sm" onClick={() => void refresh()}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {bridge ? (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <label htmlFor="printer-select" className="text-sm font-medium text-foreground">
                    Impressora instalada nesta máquina
                  </label>
                  <Select
                    id="printer-select"
                    value={selected}
                    onChange={(e) => void choosePrinter(e.target.value)}
                  >
                    <option value="">— Escolher impressora —</option>
                    {printers.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.displayName}
                        {p.isDefault ? ' (padrão do Windows)' : ''}
                      </option>
                    ))}
                    {/* Impressora salva que sumiu da lista (driver desinstalado) */}
                    {selected && !printers.some((p) => p.name === selected) && (
                      <option value={selected}>{selected}</option>
                    )}
                  </Select>
                  {printers.length === 0 && (
                    <p className="text-xs text-muted-foreground">
                      Nenhuma impressora instalada encontrada. Instale o driver da térmica no Windows.
                    </p>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3 self-end sm:grid-cols-4">
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-xs text-muted-foreground">Impressos</p>
                    <p className="text-xl font-bold text-foreground">{local?.printed ?? 0}</p>
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-xs text-muted-foreground">Falhas</p>
                    <p className="text-xl font-bold text-foreground">{local?.failed ?? 0}</p>
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-xs text-muted-foreground">Na fila</p>
                    <p className="text-xl font-bold text-foreground">{backend?.pending_jobs ?? 0}</p>
                  </div>
                  {/* Vencido = cupom que ficou para trás e NÃO volta sozinho. */}
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-xs text-muted-foreground">Vencidos</p>
                    <p
                      className={`text-xl font-bold ${
                        (backend?.expired_jobs ?? 0) > 0 ? 'text-warning' : 'text-foreground'
                      }`}
                    >
                      {backend?.expired_jobs ?? 0}
                    </p>
                  </div>
                </div>
              </div>

              {local?.lastError && (
                <Alert variant="error" title="Último erro da impressora">
                  {local.lastError}
                </Alert>
              )}

              {(local?.replayed ?? 0) > 0 && (
                <p className="text-xs text-muted-foreground">
                  {local?.replayed} cupom(ns) já haviam saído nesta máquina e não foram repetidos
                  (o relato para o servidor se perdeu).
                </p>
              )}

              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => void testPrint()} disabled={testing || !configured}>
                  {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                  Testar impressão
                </Button>
                {!configured && (
                  <span className="text-xs text-muted-foreground">
                    Escolha uma impressora para habilitar o teste.
                  </span>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Estado da fila no servidor: {backend?.pending_jobs ?? 0} pendente(s),{' '}
              {backend?.failed_jobs ?? 0} com falha, {backend?.total_jobs_today ?? 0} impresso(s) hoje.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Fila de impressão
            {needingAttention > 0 && (
              <Badge variant="warning" className="ml-1">
                {needingAttention} aguardando atenção
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Carregando a fila…</p>
          ) : jobs.length === 0 ? (
            <EmptyState
              icon={Printer}
              title="Nenhum cupom na fila"
              description="Pedidos pagos e impressões pelo botão Imprimir aparecem aqui, com o resultado de cada tentativa."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pedido</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Tentativas</TableHead>
                  <TableHead>Quando</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => {
                  const st = JOB_LABEL[job.status] ?? { label: job.status, variant: 'secondary' as const }
                  return (
                    <TableRow key={job.id}>
                      <TableCell className="font-medium">
                        #{job.order_id}
                        {job.is_reprint && (
                          <Badge variant="outline" className="ml-2 text-xs">
                            reimpressão
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant={st.variant}>{st.label}</Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{job.attempts}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {when(job.completed_at ?? job.created_at)}
                      </TableCell>
                      <TableCell className="max-w-[240px] truncate text-muted-foreground" title={job.error ?? ''}>
                        {job.error || '—'}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={job.status === 'PENDING' || job.status === 'PROCESSING' || retrying === job.id}
                          onClick={() => void retryJob(job)}
                        >
                          <RotateCcw className="h-4 w-4" />
                          {job.status === 'COMPLETED' || job.status === 'EXPIRED'
                            ? 'Reimprimir'
                            : 'Tentar de novo'}
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
