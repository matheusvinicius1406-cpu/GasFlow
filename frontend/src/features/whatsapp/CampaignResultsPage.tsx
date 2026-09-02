/**
 * Campaign Results — Detail view of a single campaign.
 *
 * Shows:
 * - Campaign info (name, status, message)
 * - Progress bar with live stats
 * - Action buttons (pause, resume, cancel)
 * - Recipient list with individual statuses
 */

import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Pause,
  Play,
  X,
  CheckCircle,
  AlertTriangle,
  Clock,
  Send,
  Users,
  Loader2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { apiClient } from '@/lib/api/client'

// ── Types ────────────────────────────────────────────────

interface CampaignFull {
  id: number
  name: string
  message: string
  list_id: number
  status: string
  protection: string
  created_at: string
  started_at: string | null
  completed_at: string | null
}

interface CampaignResults {
  total: number
  pending: number
  processing: number
  sent: number
  failed: number
  cancelled: number
}

interface CampaignRecipient {
  campaign_id: number
  customer_id: number
  status: string
  attempts: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  sent_at: string | null
  last_error: string | null
  error: string | null
  provider_message_id: string | null
}

// ── Status Config ────────────────────────────────────────

const STATUS_CONFIG: Record<
  string,
  {
    label: string
    variant: 'success' | 'warning' | 'destructive' | 'info' | 'secondary'
  }
> = {
  DRAFT: { label: 'Rascunho', variant: 'secondary' },
  RUNNING: { label: 'Em execução', variant: 'info' },
  PAUSED: { label: 'Pausada', variant: 'warning' },
  COMPLETED: { label: 'Concluída', variant: 'success' },
  CANCELLED: { label: 'Cancelada', variant: 'destructive' },
  FAILED: { label: 'Falhou', variant: 'destructive' },
}

const RECIPIENT_STATUS: Record<
  string,
  { label: string; variant: 'success' | 'warning' | 'destructive' | 'info' | 'secondary' }
> = {
  PENDING: { label: 'Pendente', variant: 'secondary' },
  PROCESSING: { label: 'Processando', variant: 'info' },
  SENT: { label: 'Enviado', variant: 'success' },
  FAILED: { label: 'Falhou', variant: 'destructive' },
  CANCELLED: { label: 'Cancelado', variant: 'warning' },
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('pt-BR')
}

// ── Main Page ────────────────────────────────────────────

export function CampaignResultsPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const campaignId = Number(id)

  const [campaign, setCampaign] = useState<CampaignFull | null>(null)
  const [results, setResults] = useState<CampaignResults | null>(null)
  const [recipients, setRecipients] = useState<CampaignRecipient[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    if (!campaignId) return
    try {
      const [campaignRes, resultsRes, recipientsRes] = await Promise.all([
        apiClient.get(`/whatsapp/campaigns/${campaignId}`),
        apiClient.get(`/whatsapp/campaigns/${campaignId}/results`),
        apiClient.get(`/whatsapp/campaigns/${campaignId}/recipients`),
      ])
      setCampaign(campaignRes.data)
      setResults(resultsRes.data.results)
      setRecipients(recipientsRes.data.recipients || [])
      setError(null)
    } catch {
      setError('Campanha não encontrada.')
    } finally {
      setLoading(false)
    }
  }, [campaignId])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Poll when running
  useEffect(() => {
    if (!campaign || campaign.status !== 'RUNNING') return
    const interval = setInterval(fetchData, 3000)
    return () => clearInterval(interval)
  }, [campaign?.status, fetchData])

  // Actions
  const handlePause = async () => {
    setActionLoading(true)
    try {
      await apiClient.post(`/whatsapp/campaigns/${campaignId}/pause`)
      fetchData()
    } catch {
      // silent
    } finally {
      setActionLoading(false)
    }
  }

  const handleResume = async () => {
    setActionLoading(true)
    try {
      await apiClient.post(`/whatsapp/campaigns/${campaignId}/start`)
      fetchData()
    } catch {
      // silent
    } finally {
      setActionLoading(false)
    }
  }

  const handleCancel = async () => {
    if (!confirm('Tem certeza que deseja cancelar esta campanha?')) return
    setActionLoading(true)
    try {
      await apiClient.post(`/whatsapp/campaigns/${campaignId}/cancel`)
      fetchData()
    } catch {
      // silent
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error || !campaign) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Button onClick={() => navigate('/whatsapp')} variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-2xl font-bold text-foreground">Campanha</h1>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
            <h3 className="text-lg font-semibold">{error || 'Não encontrada'}</h3>
            <Button onClick={() => navigate('/whatsapp')} className="mt-4" variant="outline">
              Voltar
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const status = STATUS_CONFIG[campaign.status] || {
    label: campaign.status,
    variant: 'secondary' as const,
  }

  const progress =
    results && results.total > 0
      ? Math.round(((results.sent + results.failed) / results.total) * 100)
      : 0

  const isRunning = campaign.status === 'RUNNING'
  const isPaused = campaign.status === 'PAUSED'
  const isDraft = campaign.status === 'DRAFT'
  const isActive = isRunning || isPaused || isDraft

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            onClick={() => navigate('/whatsapp')}
            variant="ghost"
            size="sm"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight text-foreground">
                {campaign.name}
              </h1>
              <Badge variant={status.variant}>{status.label}</Badge>
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">
              Campanha #{campaign.id}
            </p>
          </div>
        </div>

        {/* Actions */}
        {isActive && (
          <div className="flex gap-2">
            {isRunning && (
              <Button
                onClick={handlePause}
                variant="outline"
                disabled={actionLoading}
              >
                {actionLoading ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Pause className="h-4 w-4 mr-2" />
                )}
                Pausar
              </Button>
            )}
            {isPaused && (
              <Button onClick={handleResume} disabled={actionLoading}>
                {actionLoading ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                Retomar
              </Button>
            )}
            <Button
              onClick={handleCancel}
              variant="destructive"
              disabled={actionLoading}
            >
              <X className="h-4 w-4 mr-2" />
              Cancelar
            </Button>
          </div>
        )}
      </div>

      {/* Progress */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-muted-foreground">Progresso</span>
            <span className="text-sm font-bold text-foreground">{progress}%</span>
          </div>
          <div className="h-3 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Stats Grid */}
      {results && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <div className="rounded-lg bg-primary/10 p-2">
                  <Send className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {results.sent}
                  </p>
                  <p className="text-xs text-muted-foreground">Enviados</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <div className="rounded-lg bg-success/10 p-2">
                  <CheckCircle className="h-5 w-5 text-success" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {results.total > 0
                      ? Math.round((results.sent / results.total) * 100)
                      : 0}
                    %
                  </p>
                  <p className="text-xs text-muted-foreground">Taxa de sucesso</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <div className="rounded-lg bg-muted p-2">
                  <Clock className="h-5 w-5 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {results.pending + results.processing}
                  </p>
                  <p className="text-xs text-muted-foreground">Pendentes</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <div className="rounded-lg bg-destructive/10 p-2">
                  <X className="h-5 w-5 text-destructive" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {results.failed}
                  </p>
                  <p className="text-xs text-muted-foreground">Falhas</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <div className="rounded-lg bg-warning/10 p-2">
                  <AlertTriangle className="h-5 w-5 text-warning" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {results.cancelled}
                  </p>
                  <p className="text-xs text-muted-foreground">Cancelados</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <div className="rounded-lg bg-info/10 p-2">
                  <Users className="h-5 w-5 text-info" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {results.total}
                  </p>
                  <p className="text-xs text-muted-foreground">Total</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Message Preview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Mensagem Enviada</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-xl bg-[#DCF8C6] dark:bg-[#1D4D2B] p-4 max-w-md shadow-sm">
            <p className="text-sm text-black dark:text-white whitespace-pre-wrap leading-relaxed">
              {campaign.message}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Timing */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-6 text-sm text-muted-foreground">
            <span>Criada: {formatDate(campaign.created_at)}</span>
            {campaign.started_at && (
              <span>Início: {formatDate(campaign.started_at)}</span>
            )}
            {campaign.completed_at && (
              <span>Fim: {formatDate(campaign.completed_at)}</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Recipients List */}
      {recipients.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5 text-primary" />
              Destinatários ({recipients.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 text-muted-foreground font-medium">
                      Cliente ID
                    </th>
                    <th className="text-left py-2 text-muted-foreground font-medium">
                      Status
                    </th>
                    <th className="text-left py-2 text-muted-foreground font-medium">
                      Tentativas
                    </th>
                    <th className="text-left py-2 text-muted-foreground font-medium">
                      Enviado em
                    </th>
                    <th className="text-left py-2 text-muted-foreground font-medium">
                      Erro
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {recipients.map((r) => {
                    const rStatus = RECIPIENT_STATUS[r.status] || {
                      label: r.status,
                      variant: 'secondary' as const,
                    }
                    return (
                      <tr
                        key={r.customer_id}
                        className="border-b border-border/50"
                      >
                        <td className="py-2 text-foreground">
                          #{r.customer_id}
                        </td>
                        <td className="py-2">
                          <Badge variant={rStatus.variant} className="text-xs">
                            {rStatus.label}
                          </Badge>
                        </td>
                        <td className="py-2 text-muted-foreground">
                          {r.attempts}
                        </td>
                        <td className="py-2 text-muted-foreground">
                          {r.sent_at ? formatDate(r.sent_at) : '—'}
                        </td>
                        <td className="py-2 text-destructive text-xs max-w-[200px] truncate">
                          {r.error || r.last_error || '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
