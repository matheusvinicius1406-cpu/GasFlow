/**
 * Campaign Wizard — Multi-step campaign creation flow.
 *
 * Steps:
 * 1. Details   — name, description
 * 2. Template  — select message template
 * 3. Audience  — select list/contacts
 * 4. Review    — summary + preview + confirm
 * 5. Results   — progress tracking after dispatch
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  Send,
  CheckCircle,
  AlertTriangle,
  FileText,
  Users,
  Eye,
  Rocket,
  Clock,
  MessageSquare,
  X,
  Loader2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { apiClient } from '@/lib/api/client'

// ── Types ────────────────────────────────────────────────

interface CampaignList {
  id: number
  name: string
  description: string | null
  contactCount: number
  customerCount: number
  created_at: string
}



interface CampaignResults {
  total: number
  pending: number
  processing: number
  sent: number
  failed: number
  cancelled: number
}

interface CampaignPreview {
  campaignId: number
  name: string
  listId: number
  selected: number
  eligible: number
  optedOut: number
  blocked: number
  duplicates: number
  message: string
}

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

// ── Step Indicator ───────────────────────────────────────

const STEPS = [
  { key: 'details', label: 'Detalhes', icon: FileText },
  { key: 'template', label: 'Mensagem', icon: MessageSquare },
  { key: 'audience', label: 'Público', icon: Users },
  { key: 'review', label: 'Revisão', icon: Eye },
  { key: 'results', label: 'Resultados', icon: CheckCircle },
]

function StepIndicator({ current, completed }: { current: number; completed: boolean[] }) {
  return (
    <div className="flex items-center justify-between mb-8">
      {STEPS.map((step, i) => {
        const Icon = step.icon
        const isActive = i === current
        const isDone = completed[i]
        return (
          <div key={step.key} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  'flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all',
                  isDone
                    ? 'border-success bg-success text-white'
                    : isActive
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-muted bg-muted text-muted-foreground'
                )}
              >
                {isDone ? (
                  <CheckCircle className="h-5 w-5" />
                ) : (
                  <Icon className="h-5 w-5" />
                )}
              </div>
              <span
                className={cn(
                  'text-xs mt-1.5 font-medium hidden sm:block',
                  isActive ? 'text-foreground' : 'text-muted-foreground'
                )}
              >
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={cn(
                  'h-0.5 w-8 sm:w-16 mx-2 mt-[-18px] sm:mt-0',
                  isDone ? 'bg-success' : 'bg-muted'
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── cn helper ────────────────────────────────────────────

function cn(...classes: (string | boolean | undefined | null)[]) {
  return classes.filter(Boolean).join(' ')
}

// ── Step 1: Details ──────────────────────────────────────

function DetailsStep({
  name,
  setName,
  errors,
}: {
  name: string
  setName: (v: string) => void
  errors: Record<string, string>
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-primary" />
          Detalhes da Campanha
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            Nome da Campanha <span className="text-destructive">*</span>
          </label>
          <Input
            placeholder="Ex: Promoção de Inverno, Liquidação de Estoque..."
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          {errors.name && (
            <p className="text-sm text-destructive">{errors.name}</p>
          )}
          <p className="text-xs text-muted-foreground">
            Um nome claro ajuda a identificar a campanha no histórico.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Step 2: Template ─────────────────────────────────────

function TemplateStep({
  message,
  setMessage,
  previewMessage,
  errors,
}: {
  message: string
  setMessage: (v: string) => void
  previewMessage: string
  errors: Record<string, string>
}) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-primary" />
            Mensagem da Campanha
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              Mensagem <span className="text-destructive">*</span>
            </label>
            <Textarea
              placeholder="Digite a mensagem que será enviada aos destinatários..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={8}
              className="font-mono text-sm"
            />
            {errors.message && (
              <p className="text-sm text-destructive">{errors.message}</p>
            )}
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                {message.length}/4096 caracteres
              </p>
              <p className="text-xs text-muted-foreground">
                Mensagens longas são enviadas em partes pelo WhatsApp.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-muted-foreground">
            Pré-visualização
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-xl bg-[#DCF8C6] dark:bg-[#1D4D2B] p-4 max-w-sm mx-auto shadow-sm">
            <p className="text-sm text-black dark:text-white whitespace-pre-wrap leading-relaxed">
              {previewMessage || (
                <span className="text-black/40 dark:text-white/40 italic">
                  A mensagem aparecerá aqui...
                </span>
              )}
            </p>
            <p className="text-[10px] text-black/40 dark:text-white/40 text-right mt-2">
              {new Date().toLocaleTimeString('pt-BR', {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </p>
          </div>
          <p className="text-xs text-muted-foreground text-center mt-3">
            Pré-visualização simulando aparência WhatsApp.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

// ── Step 3: Audience ─────────────────────────────────────

function AudienceStep({
  lists,
  selectedListId,
  setSelectedListId,
  loading,
  errors,
}: {
  lists: CampaignList[]
  selectedListId: number | null
  setSelectedListId: (id: number) => void
  loading: boolean
  errors: Record<string, string>
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (lists.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <Users className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">Nenhuma lista disponível</h3>
          <p className="text-sm text-muted-foreground mt-2 text-center max-w-md">
            Crie listas de contatos no WhatsApp antes de criar uma campanha.
            Listas são gerenciadas pelo serviço WhatsApp.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-5 w-5 text-primary" />
          Selecionar Público
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Selecione a lista de destinatários para esta campanha.
        </p>
        {errors.list && (
          <p className="text-sm text-destructive">{errors.list}</p>
        )}

        <div className="space-y-2">
          {lists.map((list) => {
            const isSelected = selectedListId === list.id
            return (
              <button
                key={list.id}
                onClick={() => setSelectedListId(list.id)}
                className={cn(
                  'w-full flex items-center justify-between rounded-lg border p-4 text-left transition-all',
                  isSelected
                    ? 'border-primary bg-primary/5 ring-1 ring-primary'
                    : 'border-border hover:border-primary/50 hover:bg-accent/50'
                )}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      'flex h-10 w-10 items-center justify-center rounded-lg',
                      isSelected ? 'bg-primary/10' : 'bg-muted'
                    )}
                  >
                    <Users
                      className={cn(
                        'h-5 w-5',
                        isSelected ? 'text-primary' : 'text-muted-foreground'
                      )}
                    />
                  </div>
                  <div>
                    <p className="font-medium text-foreground">{list.name}</p>
                    {list.description && (
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {list.description}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className="text-lg font-bold text-foreground">
                      {list.customerCount || list.contactCount || 0}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {list.customerCount > 0 ? 'clientes' : 'contatos'}
                    </p>
                  </div>
                  {isSelected && (
                    <CheckCircle className="h-5 w-5 text-primary" />
                  )}
                </div>
              </button>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Step 4: Review ───────────────────────────────────────

function ReviewStep({
  name,
  message,
  lists,
  selectedListId,
  preview,
  loading,
}: {
  name: string
  message: string
  lists: CampaignList[]
  selectedListId: number | null
  preview: CampaignPreview | null
  loading: boolean
}) {
  const selectedList = lists.find((l) => l.id === selectedListId)

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5 text-primary" />
            Revisão da Campanha
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Summary */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Nome</p>
              <p className="font-medium text-foreground">{name}</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Lista</p>
              <p className="font-medium text-foreground">
                {selectedList?.name || '—'}
              </p>
            </div>
          </div>

          {/* Message Preview */}
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Mensagem</p>
            <div className="rounded-lg bg-muted p-3">
              <p className="text-sm text-foreground whitespace-pre-wrap font-mono">
                {message}
              </p>
            </div>
          </div>

          {/* Recipient Stats */}
          {preview && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Destinatários
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="rounded-lg bg-muted p-3 text-center">
                  <p className="text-2xl font-bold text-foreground">
                    {preview.eligible}
                  </p>
                  <p className="text-xs text-muted-foreground">Elegíveis</p>
                </div>
                <div className="rounded-lg bg-muted p-3 text-center">
                  <p className="text-2xl font-bold text-warning">
                    {preview.optedOut}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Opt-out
                  </p>
                </div>
                <div className="rounded-lg bg-muted p-3 text-center">
                  <p className="text-2xl font-bold text-destructive">
                    {preview.blocked}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Bloqueados
                  </p>
                </div>
                <div className="rounded-lg bg-muted p-3 text-center">
                  <p className="text-2xl font-bold text-muted-foreground">
                    {preview.duplicates}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Duplicados
                  </p>
                </div>
              </div>
            </div>
          )}

          {loading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Carregando pré-visualização...
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ── Step 5: Results ──────────────────────────────────────

function ResultsStep({
  campaign,
  results,
  loading,
}: {
  campaign: CampaignFull | null
  results: CampaignResults | null
  loading: boolean
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!campaign || !results) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <AlertTriangle className="h-12 w-12 text-warning mb-4" />
          <h3 className="text-lg font-semibold">Dados indisponíveis</h3>
          <p className="text-sm text-muted-foreground mt-2">
            Não foi possível carregar os resultados da campanha.
          </p>
        </CardContent>
      </Card>
    )
  }

  const progress =
    results.total > 0
      ? Math.round(((results.sent + results.failed) / results.total) * 100)
      : 0
  const successRate =
    results.total > 0
      ? Math.round((results.sent / results.total) * 100)
      : 0

  const statusConfig: Record<
    string,
    { label: string; variant: 'success' | 'warning' | 'destructive' | 'info' | 'secondary' }
  > = {
    DRAFT: { label: 'Rascunho', variant: 'secondary' },
    RUNNING: { label: 'Em execução', variant: 'info' },
    PAUSED: { label: 'Pausada', variant: 'warning' },
    COMPLETED: { label: 'Concluída', variant: 'success' },
    CANCELLED: { label: 'Cancelada', variant: 'destructive' },
    FAILED: { label: 'Falhou', variant: 'destructive' },
  }

  const status = statusConfig[campaign.status] || {
    label: campaign.status,
    variant: 'secondary' as const,
  }

  return (
    <div className="space-y-4">
      {/* Status Header */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-foreground">
                {campaign.name}
              </h3>
              <p className="text-sm text-muted-foreground mt-0.5">
                Campanha #{campaign.id}
              </p>
            </div>
            <Badge variant={status.variant}>{status.label}</Badge>
          </div>

          {/* Progress Bar */}
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-muted-foreground">Progresso</span>
              <span className="text-sm font-bold text-foreground">
                {progress}%
              </span>
            </div>
            <div className="h-3 w-full rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-primary transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats Grid */}
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
                  {successRate}%
                </p>
                <p className="text-xs text-muted-foreground">
                  Taxa de sucesso
                </p>
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
                <p className="text-xs text-muted-foreground">
                  Total destinatários
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Timing */}
      {(campaign.started_at || campaign.completed_at) && (
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              {campaign.started_at && (
                <span>
                  Início:{' '}
                  {new Date(campaign.started_at).toLocaleString('pt-BR')}
                </span>
              )}
              {campaign.completed_at && (
                <span>
                  Fim:{' '}
                  {new Date(campaign.completed_at).toLocaleString('pt-BR')}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── Main Wizard ──────────────────────────────────────────

export function CampaignWizardPage() {
  const navigate = useNavigate()

  // Wizard state
  const [step, setStep] = useState(0)
  const [completedSteps, setCompletedSteps] = useState([false, false, false, false, false])

  // Form data
  const [name, setName] = useState('')
  const [message, setMessage] = useState('')
  const [selectedListId, setSelectedListId] = useState<number | null>(null)

  // Data
  const [lists, setLists] = useState<CampaignList[]>([])
  const [listsLoading, setListsLoading] = useState(true)
  const [preview, setPreview] = useState<CampaignPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [createdCampaign, setCreatedCampaign] = useState<CampaignFull | null>(null)
  const [results, setResults] = useState<CampaignResults | null>(null)
  const [resultsLoading, setResultsLoading] = useState(false)

  // UI state
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Fetch lists
  useEffect(() => {
    const fetchLists = async () => {
      try {
        const { data } = await apiClient.get('/whatsapp/lists')
        setLists(data.lists || [])
      } catch {
        // silent
      } finally {
        setListsLoading(false)
      }
    }
    fetchLists()
  }, [])

  // Fetch preview when list changes
  useEffect(() => {
    if (!selectedListId || step !== 3) return
    const fetchPreview = async () => {
      setPreviewLoading(true)
      try {
        const { data } = await apiClient.get(`/whatsapp/lists/${selectedListId}`)
        setPreview({
          campaignId: 0,
          name,
          listId: selectedListId,
          selected: data.customerCount || data.contactCount || 0,
          eligible: data.customerCount || data.contactCount || 0,
          optedOut: 0,
          blocked: 0,
          duplicates: 0,
          message,
        })
      } catch {
        // silent
      } finally {
        setPreviewLoading(false)
      }
    }
    fetchPreview()
  }, [selectedListId, step, name, message])

  // Poll results when on results step and campaign is running
  useEffect(() => {
    if (step !== 4 || !createdCampaign) return
    if (createdCampaign.status !== 'RUNNING') return

    const fetchResults = async () => {
      try {
        const { data } = await apiClient.get(
          `/whatsapp/campaigns/${createdCampaign.id}/results`
        )
        setResults(data.results)
        // Update campaign status
        setCreatedCampaign((prev) =>
          prev ? { ...prev, status: data.campaign?.status ?? prev.status } : prev
        )
      } catch {
        // silent
      }
    }

    fetchResults()
    const interval = setInterval(fetchResults, 3000)
    return () => clearInterval(interval)
  }, [step, createdCampaign?.id, createdCampaign?.status])

  // Also fetch final results when campaign completes
  useEffect(() => {
    if (step !== 4 || !createdCampaign) return
    if (!['COMPLETED', 'FAILED', 'CANCELLED'].includes(createdCampaign.status)) return

    const fetchFinalResults = async () => {
      setResultsLoading(true)
      try {
        const { data } = await apiClient.get(
          `/whatsapp/campaigns/${createdCampaign.id}/results`
        )
        setResults(data.results)
        setCreatedCampaign(data.campaign)
      } catch {
        // silent
      } finally {
        setResultsLoading(false)
      }
    }
    fetchFinalResults()
  }, [step, createdCampaign?.id, createdCampaign?.status])

  // Validation
  const validateStep = (s: number): boolean => {
    const newErrors: Record<string, string> = {}

    if (s === 0) {
      if (!name.trim()) newErrors.name = 'Nome é obrigatório.'
    } else if (s === 1) {
      if (!message.trim()) newErrors.message = 'Mensagem é obrigatória.'
      if (message.length > 4096) newErrors.message = 'Mensagem excede 4096 caracteres.'
    } else if (s === 2) {
      if (!selectedListId) newErrors.list = 'Selecione uma lista.'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  // Navigation
  const handleNext = () => {
    if (!validateStep(step)) return

    const newCompleted = [...completedSteps]
    newCompleted[step] = true
    setCompletedSteps(newCompleted)
    setStep(step + 1)
  }

  const handleBack = () => {
    setStep(step - 1)
  }

  // Submit campaign
  const handleSubmit = async () => {
    if (!selectedListId) return
    setSubmitting(true)
    setSubmitError(null)

    try {
      // Create campaign
      const { data: created } = await apiClient.post('/whatsapp/campaigns', {
        name: name.trim(),
        message: message.trim(),
        listId: selectedListId,
      })
      setCreatedCampaign(created)

      // Start campaign
      await apiClient.post(`/whatsapp/campaigns/${created.id}/start`)

      // Move to results
      const newCompleted = [...completedSteps]
      newCompleted[3] = true
      setCompletedSteps(newCompleted)
      setStep(4)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { error?: string } } })?.response?.data
          ?.error || 'Erro ao criar campanha.'
      setSubmitError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button
          onClick={() => navigate('/whatsapp')}
          variant="ghost"
          size="sm"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Nova Campanha
          </h1>
          <p className="text-sm text-muted-foreground">
            Crie e envie uma campanha WhatsApp para seus clientes.
          </p>
        </div>
      </div>

      {/* Step Indicator */}
      <StepIndicator current={step} completed={completedSteps} />

      {/* Step Content */}
      {step === 0 && (
        <DetailsStep name={name} setName={setName} errors={errors} />
      )}

      {step === 1 && (
        <TemplateStep
          message={message}
          setMessage={setMessage}
          previewMessage={message}
          errors={errors}
        />
      )}

      {step === 2 && (
        <AudienceStep
          lists={lists}
          selectedListId={selectedListId}
          setSelectedListId={setSelectedListId}
          loading={listsLoading}
          errors={errors}
        />
      )}

      {step === 3 && (
        <ReviewStep
          name={name}
          message={message}
          lists={lists}
          selectedListId={selectedListId}
          preview={preview}
          loading={previewLoading}
        />
      )}

      {step === 4 && (
        <ResultsStep
          campaign={createdCampaign}
          results={results}
          loading={resultsLoading}
        />
      )}

      {/* Error */}
      {submitError && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3">
          <AlertTriangle className="h-4 w-4 text-destructive" />
          <p className="text-sm text-destructive">{submitError}</p>
        </div>
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <div>
          {step > 0 && step < 4 && (
            <Button onClick={handleBack} variant="outline">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Voltar
            </Button>
          )}
        </div>
        <div className="flex gap-2">
          {step < 3 && (
            <Button onClick={handleNext}>
              Próximo
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          )}
          {step === 3 && (
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Rocket className="h-4 w-4 mr-2" />
              )}
              Disparar Campanha
            </Button>
          )}
          {step === 4 && (
            <Button onClick={() => navigate('/whatsapp')}>
              <CheckCircle className="h-4 w-4 mr-2" />
              Concluir
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
