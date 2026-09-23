import { useCallback, useEffect, useState } from 'react'
import { Workflow, Play, Pause, XCircle, ShieldAlert, Check, Ban, Power } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { apiClient } from '@/lib/api/client'
import { useToast } from '@/components/ui/Toast'

/**
 * Automações (workflows e aprovações) — execução de workflows internos.
 *
 * É o **outro** "Automações": o menu do WhatsApp leva às regras de mensagem
 * (`/automation/whatsapp/*`), esta tela é o motor de workflow/aprovações
 * (`/automation/*`). O backend tinha tudo isso e nenhuma tela — inclusive o
 * `POST /automation/runs/{id}/cancel`, que não tinha de onde ser chamado.
 *
 * Dois avisos que a tela dá porque importam de verdade:
 * - os runs vivem **em memória do processo** (`_workflow_engine._run_history`);
 *   reiniciar o backend limpa a lista;
 * - o **kill switch** derruba toda a automação em execução, não só a desta tela.
 */
interface WorkflowDefinition {
  id: string
  name: string
  status: string
  steps: number
}

interface WorkflowRun {
  id: string
  workflow_id: string
  status: string
  started_at: string | null
}

interface Approval {
  id: string
  action: string
  status: string
  risk_level: string
  created_at: string
}

const TERMINAL_RUN_STATES = ['COMPLETED', 'FAILED', 'CANCELLED']

const RUN_STATUS_VARIANTS: Record<string, 'success' | 'destructive' | 'warning' | 'secondary' | 'info'> = {
  COMPLETED: 'success',
  FAILED: 'destructive',
  CANCELLED: 'secondary',
  PAUSED: 'warning',
  AWAITING_APPROVAL: 'warning',
  RUNNING: 'info',
}

const RISK_VARIANTS: Record<string, 'destructive' | 'warning' | 'secondary'> = {
  HIGH: 'destructive',
  MEDIUM: 'warning',
  LOW: 'secondary',
}

export function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([])
  const [runs, setRuns] = useState<WorkflowRun[]>([])
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [killSwitch, setKillSwitch] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [activeTab, setActiveTab] = useState<'runs' | 'approvals' | 'workflows'>('runs')
  const [busy, setBusy] = useState<string | null>(null)
  const { success, error: toastError } = useToast()

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const [wfRes, runsRes, apprRes, ksRes] = await Promise.all([
        apiClient.get('/automation/workflows'),
        apiClient.get('/automation/runs'),
        apiClient.get('/automation/approvals'),
        apiClient.get('/automation/kill-switch'),
      ])
      setWorkflows(wfRes.data.workflows || [])
      setRuns(runsRes.data.runs || [])
      setApprovals(apprRes.data.approvals || [])
      setKillSwitch(Boolean(ksRes.data.active))
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  /** 400 aqui é regra do motor ("Cannot pause/cancel run"), não erro de rede. */
  function reportActionError(err: unknown, what: string) {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 400) {
      toastError(`Não foi possível ${what}`, 'O motor recusou — o run pode já ter terminado.')
      void fetchData()
      return
    }
    if (status === 403) {
      toastError('Sem permissão', `Seu usuário não pode ${what} automações.`)
      return
    }
    toastError(`Erro ao ${what}`, 'Nada foi alterado. Tente novamente.')
  }

  async function handlePauseRun(run: WorkflowRun) {
    setBusy(`pause-${run.id}`)
    try {
      await apiClient.post(`/automation/runs/${run.id}/pause`)
      success('Run pausado', run.workflow_id)
      await fetchData()
    } catch (err) {
      reportActionError(err, 'pausar o run')
    } finally {
      setBusy(null)
    }
  }

  async function handleCancelRun(run: WorkflowRun) {
    const confirmed = window.confirm(
      `Cancelar o run ${run.id.slice(0, 8)} (${run.workflow_id})?\n\n` +
      'Os passos restantes não são executados. O histórico do run é mantido na lista.',
    )
    if (!confirmed) return

    setBusy(`cancel-${run.id}`)
    try {
      await apiClient.post(`/automation/runs/${run.id}/cancel`)
      success('Run cancelado', run.workflow_id)
      await fetchData()
    } catch (err) {
      reportActionError(err, 'cancelar o run')
    } finally {
      setBusy(null)
    }
  }

  async function handleExecuteWorkflow(workflow: WorkflowDefinition) {
    setBusy(`exec-${workflow.id}`)
    try {
      await apiClient.post(`/automation/workflows/${workflow.id}/execute`, { context: {} })
      success('Workflow disparado', workflow.name)
      await fetchData()
    } catch (err) {
      reportActionError(err, 'executar o workflow')
    } finally {
      setBusy(null)
    }
  }

  async function handleApproval(approval: Approval, approve: boolean) {
    const confirmed = window.confirm(
      approve
        ? `Aprovar a ação "${approval.action}" (risco ${approval.risk_level})?`
        : `Rejeitar a ação "${approval.action}"? Ela não será executada.`,
    )
    if (!confirmed) return

    setBusy(`appr-${approval.id}`)
    try {
      if (approve) {
        await apiClient.post(`/automation/approvals/${approval.id}/approve`, { approved_by: 'operator' })
        success('Ação aprovada', approval.action)
      } else {
        await apiClient.post(`/automation/approvals/${approval.id}/reject`)
        success('Ação rejeitada', approval.action)
      }
      await fetchData()
    } catch (err) {
      reportActionError(err, approve ? 'aprovar a ação' : 'rejeitar a ação')
    } finally {
      setBusy(null)
    }
  }

  async function handleKillSwitch() {
    const next = !killSwitch
    const confirmed = window.confirm(
      next
        ? 'Ligar o KILL SWITCH?\n\nToda a automação para de executar imediatamente — workflows e agentes, de todos os usuários.'
        : 'Desligar o kill switch e permitir que a automação volte a executar?',
    )
    if (!confirmed) return

    setBusy('kill-switch')
    try {
      const res = await apiClient.post('/automation/kill-switch', { active: next })
      setKillSwitch(Boolean(res.data.active))
      if (next) toastError('Kill switch LIGADO', 'Nenhuma automação vai executar até ser desligado.')
      else success('Kill switch desligado', 'A automação volta a executar normalmente.')
    } catch (err) {
      reportActionError(err, 'alternar o kill switch')
    } finally {
      setBusy(null)
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
    return <ErrorState message="Não foi possível carregar as automações." onRetry={() => fetchData()} />
  }

  const pendingApprovals = approvals.filter(a => a.status === 'PENDING')

  return (
    <Page>
      <PageHeader>
        <PageTitle subtitle="Workflows internos, aprovações e kill switch">
          Automações (workflows)
        </PageTitle>
        <PageActions>
          <Button
            variant={killSwitch ? 'destructive' : 'outline'}
            onClick={handleKillSwitch}
            disabled={busy === 'kill-switch'}
            aria-label={killSwitch ? 'Desligar kill switch' : 'Ligar kill switch'}
          >
            <Power className="h-4 w-4 mr-1" />
            {killSwitch ? 'Kill switch LIGADO' : 'Kill switch'}
          </Button>
        </PageActions>
      </PageHeader>

      {killSwitch && (
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <ShieldAlert className="h-5 w-5 text-destructive" />
            <div>
              <p className="text-sm font-medium">Automação suspensa</p>
              <p className="text-xs text-muted-foreground">
                Enquanto o kill switch estiver ligado, nenhum workflow ou agente executa.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex gap-2 border-b pb-2 overflow-x-auto">
        {([
          { key: 'runs' as const, label: `Execuções (${runs.length})` },
          { key: 'approvals' as const, label: `Aprovações (${pendingApprovals.length})` },
          { key: 'workflows' as const, label: `Workflows (${workflows.length})` },
        ]).map(tab => (
          <Button
            key={tab.key}
            variant={activeTab === tab.key ? 'default' : 'ghost'}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {activeTab === 'runs' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Workflow className="h-5 w-5" /> Execuções
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* Os runs vivem na memória do processo — reiniciar o backend limpa a lista. */}
            <p className="mb-3 text-xs text-muted-foreground">
              Histórico em memória do servidor: reiniciar o backend zera esta lista.
            </p>
            {runs.length === 0 ? (
              <EmptyState
                icon={Workflow}
                title="Nenhuma execução"
                description="Dispare um workflow para ver as execuções aqui."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Run</TableHead>
                    <TableHead>Workflow</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Início</TableHead>
                    <TableHead>Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.map(run => (
                    <TableRow key={run.id}>
                      <TableCell className="font-mono text-xs">{run.id.slice(0, 8)}</TableCell>
                      <TableCell className="text-sm">{run.workflow_id}</TableCell>
                      <TableCell>
                        <Badge variant={RUN_STATUS_VARIANTS[run.status] || 'secondary'}>{run.status}</Badge>
                      </TableCell>
                      <TableCell className="text-xs">
                        {run.started_at ? new Date(run.started_at).toLocaleString('pt-BR') : '—'}
                      </TableCell>
                      <TableCell>
                        {!TERMINAL_RUN_STATES.includes(run.status) && (
                          <div className="flex flex-wrap items-center gap-1">
                            {run.status === 'RUNNING' && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handlePauseRun(run)}
                                disabled={busy === `pause-${run.id}`}
                                aria-label={`Pausar run ${run.id}`}
                              >
                                <Pause className="h-4 w-4 mr-1" />
                                {busy === `pause-${run.id}` ? 'Pausando...' : 'Pausar'}
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleCancelRun(run)}
                              disabled={busy === `cancel-${run.id}`}
                              aria-label={`Cancelar run ${run.id}`}
                              className="text-destructive hover:bg-destructive/10 focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              <XCircle className="h-4 w-4 mr-1" />
                              {busy === `cancel-${run.id}` ? 'Cancelando...' : 'Cancelar'}
                            </Button>
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === 'approvals' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5" /> Aprovações — ações de risco
            </CardTitle>
          </CardHeader>
          <CardContent>
            {approvals.length === 0 ? (
              <EmptyState
                icon={ShieldAlert}
                title="Nenhuma aprovação pendente"
                description="Ações de risco alto aparecem aqui para revisão."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ação</TableHead>
                    <TableHead>Risco</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Solicitada</TableHead>
                    <TableHead>Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {approvals.map(approval => (
                    <TableRow key={approval.id}>
                      <TableCell className="text-sm">{approval.action}</TableCell>
                      <TableCell>
                        <Badge variant={RISK_VARIANTS[approval.risk_level] || 'secondary'}>
                          {approval.risk_level}
                        </Badge>
                      </TableCell>
                      <TableCell><Badge variant="secondary">{approval.status}</Badge></TableCell>
                      <TableCell className="text-xs">
                        {new Date(approval.created_at).toLocaleString('pt-BR')}
                      </TableCell>
                      <TableCell>
                        {approval.status === 'PENDING' && (
                          <div className="flex flex-wrap items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleApproval(approval, true)}
                              disabled={busy === `appr-${approval.id}`}
                              aria-label={`Aprovar ${approval.action}`}
                            >
                              <Check className="h-4 w-4 mr-1" /> Aprovar
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleApproval(approval, false)}
                              disabled={busy === `appr-${approval.id}`}
                              aria-label={`Rejeitar ${approval.action}`}
                              className="text-destructive hover:bg-destructive/10 focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              <Ban className="h-4 w-4 mr-1" /> Rejeitar
                            </Button>
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === 'workflows' && (
        <Card>
          <CardHeader><CardTitle>Workflows definidos</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Workflow</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Passos</TableHead>
                  <TableHead>Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {workflows.map(workflow => (
                  <TableRow key={workflow.id}>
                    <TableCell>
                      <div className="text-sm font-medium">{workflow.name}</div>
                      <div className="font-mono text-xs text-muted-foreground">{workflow.id}</div>
                    </TableCell>
                    <TableCell><Badge variant="secondary">{workflow.status}</Badge></TableCell>
                    <TableCell className="text-sm">{workflow.steps}</TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleExecuteWorkflow(workflow)}
                        disabled={busy === `exec-${workflow.id}` || killSwitch}
                        aria-label={`Executar ${workflow.name}`}
                      >
                        <Play className="h-4 w-4 mr-1" />
                        {busy === `exec-${workflow.id}` ? 'Disparando...' : 'Executar'}
                      </Button>
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
