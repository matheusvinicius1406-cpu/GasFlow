/**
 * Campaign History — List of past and current campaigns.
 *
 * Shows:
 * - Campaign name
 * - Status (DRAFT, RUNNING, PAUSED, COMPLETED, CANCELLED, FAILED)
 * - List name
 * - Created date
 * - Started / Completed dates
 * - Progress (sent/total)
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus,
  RefreshCw,
  Rocket,
  Clock,
  CheckCircle,
  X,
  Pause,
  FileText,
  Eye,
  Users,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { apiClient } from '@/lib/api/client'

// ── Types ────────────────────────────────────────────────

interface CampaignRow {
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

interface CampaignResultSummary {
  total: number
  pending: number
  processing: number
  sent: number
  failed: number
  cancelled: number
}

interface CampaignWithResults extends CampaignRow {
  results?: CampaignResultSummary
  listName?: string
}

// ── Status Config ────────────────────────────────────────

const STATUS_CONFIG: Record<
  string,
  {
    label: string
    variant: 'success' | 'warning' | 'destructive' | 'info' | 'secondary'
    icon: React.ElementType
  }
> = {
  DRAFT: { label: 'Rascunho', variant: 'secondary', icon: FileText },
  RUNNING: { label: 'Em execução', variant: 'info', icon: Rocket },
  PAUSED: { label: 'Pausada', variant: 'warning', icon: Pause },
  COMPLETED: { label: 'Concluída', variant: 'success', icon: CheckCircle },
  CANCELLED: { label: 'Cancelada', variant: 'destructive', icon: X },
  FAILED: { label: 'Falhou', variant: 'destructive', icon: X },
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ── Campaign Card ────────────────────────────────────────

function CampaignCard({
  campaign,
  onViewResults,
}: {
  campaign: CampaignWithResults
  onViewResults: (id: number) => void
}) {
  const status = STATUS_CONFIG[campaign.status] || {
    label: campaign.status,
    variant: 'secondary' as const,
    icon: FileText,
  }
  const StatusIcon = status.icon
  const r = campaign.results
  const progress =
    r && r.total > 0
      ? Math.round(((r.sent + r.failed) / r.total) * 100)
      : 0

  return (
    <Card className="hover:border-primary/30 transition-colors">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div
              className={`rounded-lg p-2 flex-shrink-0 ${
                status.variant === 'success'
                  ? 'bg-success/10'
                  : status.variant === 'info'
                  ? 'bg-info/10'
                  : status.variant === 'warning'
                  ? 'bg-warning/10'
                  : status.variant === 'destructive'
                  ? 'bg-destructive/10'
                  : 'bg-muted'
              }`}
            >
              <StatusIcon
                className={`h-5 w-5 ${
                  status.variant === 'success'
                    ? 'text-success'
                    : status.variant === 'info'
                    ? 'text-info'
                    : status.variant === 'warning'
                    ? 'text-warning'
                    : status.variant === 'destructive'
                    ? 'text-destructive'
                    : 'text-muted-foreground'
                }`}
              />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-semibold text-foreground truncate">
                  {campaign.name}
                </h3>
                <Badge variant={status.variant} className="text-xs flex-shrink-0">
                  {status.label}
                </Badge>
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
                <span className="flex items-center gap-1">
                  <Users className="h-3 w-3" />
                  {campaign.listName || `Lista #${campaign.list_id}`}
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatDate(campaign.created_at)}
                </span>
                {campaign.completed_at && (
                  <span>
                    Concluída: {formatDate(campaign.completed_at)}
                  </span>
                )}
              </div>
              {campaign.message && (
                <p className="text-xs text-muted-foreground mt-1.5 truncate max-w-lg">
                  {campaign.message}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Progress indicator */}
            {r && r.total > 0 && (
              <div className="text-right hidden sm:block">
                <p className="text-sm font-bold text-foreground">
                  {r.sent}/{r.total}
                </p>
                <div className="h-1.5 w-20 rounded-full bg-muted mt-1">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}

            <Button
              onClick={() => onViewResults(campaign.id)}
              variant="ghost"
              size="sm"
            >
              <Eye className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Main Page ────────────────────────────────────────────

export function CampaignHistoryPage() {
  const navigate = useNavigate()
  const [campaigns, setCampaigns] = useState<CampaignWithResults[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  const fetchCampaigns = useCallback(async () => {
    try {
      const { data } = await apiClient.get('/whatsapp/campaigns')
      const list = (data.campaigns || []) as CampaignWithResults[]

      // Fetch results for each campaign (batch)
      const enriched = await Promise.all(
        list.map(async (c) => {
          try {
            const { data: rData } = await apiClient.get(
              `/whatsapp/campaigns/${c.id}/results`
            )
            return { ...c, results: rData.results }
          } catch {
            return c
          }
        })
      )

      setCampaigns(enriched)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCampaigns()
  }, [fetchCampaigns])

  const filtered =
    filter === 'all'
      ? campaigns
      : campaigns.filter((c) => c.status === filter)

  const handleViewResults = (id: number) => {
    navigate(`/whatsapp/campaigns/${id}`)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Campanhas
          </h1>
          <p className="text-sm text-muted-foreground">
            Gerencie e acompanhe suas campanhas WhatsApp.
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={fetchCampaigns} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => navigate('/whatsapp/campaigns/new')}>
            <Plus className="h-4 w-4 mr-2" />
            Nova Campanha
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        {[
          { key: 'all', label: 'Todas' },
          { key: 'RUNNING', label: 'Em execução' },
          { key: 'COMPLETED', label: 'Concluídas' },
          { key: 'DRAFT', label: 'Rascunhos' },
          { key: 'PAUSED', label: 'Pausadas' },
          { key: 'CANCELLED', label: 'Canceladas' },
          { key: 'FAILED', label: 'Falharam' },
        ].map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              filter === f.key
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-accent hover:text-foreground'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <LoadingSpinner size="lg" />
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Rocket className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold">
              {filter === 'all'
                ? 'Nenhuma campanha'
                : 'Nenhuma campanha com esse filtro'}
            </h3>
            <p className="text-sm text-muted-foreground mt-2 text-center max-w-md">
              {filter === 'all'
                ? 'Crie sua primeira campanha WhatsApp para alcançar seus clientes.'
                : 'Tente outro filtro ou crie uma nova campanha.'}
            </p>
            {filter === 'all' && (
              <Button
                onClick={() => navigate('/whatsapp/campaigns/new')}
                className="mt-4"
              >
                <Plus className="h-4 w-4 mr-2" />
                Criar campanha
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {filtered.map((campaign) => (
            <CampaignCard
              key={campaign.id}
              campaign={campaign}
              onViewResults={handleViewResults}
            />
          ))}
        </div>
      )}
    </div>
  )
}
