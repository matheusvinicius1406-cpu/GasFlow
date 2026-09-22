import { useState } from 'react'
import { Truck, RefreshCw, Package, MapPin, Clock, CheckCircle, XCircle, Plus, UserCog, ArrowRight, Sparkles, AlertTriangle } from 'lucide-react'
import { Alert } from '@/components/ui/Alert'
import type { DriverAlert } from '@/lib/tracking'
import { driverStockApi, type DispatchSuggestionResponse } from '@/lib/api/driverStock'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'
import { StatCard } from '@/components/ui/StatCard'
import {
  useDeliveries,
  useDeliveryDrivers,
  useDeliverySummary,
  useCreateDelivery,
  useAssignDelivery,
  useUpdateDeliveryStatus,
  useDriverLocations,
  useDeliveryEta,
  formatEta,
} from '@/lib/api/hooks'
import { DriverMap } from '@/components/map/DriverMap'
import type { DriverMapPoint } from '@/components/map/DriverMap'
import { useTrackingSocket } from '@/lib/hooks/useTrackingSocket'
import type { DeliveryDriverExtended } from '@/types'

/** Texto humano do alerta de rastreio (Fase 7.3). */
function describeAlert(alert: DriverAlert): string {
  if (alert.kind === 'STALLED') {
    return `Entregador parado há ${alert.minutes ?? 10} min com entrega em rota.`
  }
  return `Entregador ${alert.deviation_km ?? '?'} km fora da rota da entrega.`
}

const STATUS_CONFIG: Record<string, { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' | 'default'; icon: typeof Truck }> = {
  PENDING: { label: 'Pendente', variant: 'secondary', icon: Clock },
  ASSIGNED: { label: 'Atribuída', variant: 'default', icon: Package },
  DISPATCHED: { label: 'Despachada', variant: 'default', icon: Truck },
  EN_ROUTE: { label: 'Em Rota', variant: 'warning', icon: Truck },
  ARRIVED: { label: 'Chegou', variant: 'warning', icon: MapPin },
  DELIVERED: { label: 'Entregue', variant: 'success', icon: CheckCircle },
  FAILED: { label: 'Falhou', variant: 'destructive', icon: XCircle },
  CANCELLED: { label: 'Cancelada', variant: 'secondary', icon: XCircle },
  RESCHEDULED: { label: 'Reagendada', variant: 'default', icon: Clock },
}

// Valid transitions per status — matches backend DELIVERY_TRANSITIONS exactly
const VALID_TRANSITIONS: Record<string, { status: string; label: string }[]> = {
  PENDING: [
    { status: 'ASSIGNED', label: 'Atribuir' },
    { status: 'CANCELLED', label: 'Cancelar' },
  ],
  ASSIGNED: [
    { status: 'DISPATCHED', label: 'Despachar' },
    { status: 'CANCELLED', label: 'Cancelar' },
  ],
  DISPATCHED: [
    { status: 'EN_ROUTE', label: 'Iniciar Rota' },
    { status: 'CANCELLED', label: 'Cancelar' },
  ],
  EN_ROUTE: [
    { status: 'ARRIVED', label: 'Chegou' },
    { status: 'FAILED', label: 'Falha' },
    { status: 'CANCELLED', label: 'Cancelar' },
  ],
  ARRIVED: [
    { status: 'DELIVERED', label: 'Entregue' },
    { status: 'FAILED', label: 'Falha' },
    { status: 'CANCELLED', label: 'Cancelar' },
  ],
  FAILED: [
    { status: 'RESCHEDULED', label: 'Reagendar' },
    { status: 'CANCELLED', label: 'Cancelar' },
  ],
  RESCHEDULED: [
    { status: 'PENDING', label: 'Reabrir' },
  ],
}

export function DeliveriesPage() {
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [assigningId, setAssigningId] = useState<string | null>(null)
  const [selectedDriver, setSelectedDriver] = useState<string>('')
  // F7 (C3): sugestão inteligente por entrega — operador confirma
  const [suggestingId, setSuggestingId] = useState<string | null>(null)
  const [suggestion, setSuggestion] = useState<DispatchSuggestionResponse | null>(null)
  const [suggestLoading, setSuggestLoading] = useState(false)

  // Create form state
  const [newDelivery, setNewDelivery] = useState({
    order_id: '',
    customer_codigo: '',
    customer_name: '',
    notes: '',
  })

  const { data: deliveriesData, isLoading, error, refetch } = useDeliveries(statusFilter ? { status: statusFilter } : undefined)
  const { data: driversData } = useDeliveryDrivers()
  const { data: summary } = useDeliverySummary()
  const { data: locations } = useDriverLocations()
  // Fase 6: posições ao vivo por WebSocket (canal tenant:{id}). O polling fica
  // apenas como carga inicial/fallback — se o WS cair, mantém o último estado.
  const { pointsByDriver, lastByDriver, alerts, dismissAlert } = useTrackingSocket()
  const createDelivery = useCreateDelivery()
  const assignDelivery = useAssignDelivery()
  const updateStatus = useUpdateDeliveryStatus()

  const deliveries = deliveriesData?.deliveries ?? []
  const drivers = driversData?.drivers ?? []

  // F1b: pontos do mapa — posições + nome do motorista quando conhecido.
  const polledPoints: DriverMapPoint[] = (locations ?? []).map((loc) => ({
    ...loc,
    name: drivers.find(d => d.id === loc.driver_id)?.name,
  }))

  // Fase 6: a posição do WS sobrepõe a do polling (mais recente vence), sem
  // refetch — o marcador anda de forma incremental.
  const pointsById = new Map(polledPoints.map((p) => [p.driver_id, p]))
  for (const live of Object.values(lastByDriver)) {
    pointsById.set(live.driver_id, {
      driver_id: live.driver_id,
      name: drivers.find(d => d.id === live.driver_id)?.name,
      latitude: live.latitude,
      longitude: live.longitude,
      accuracy: live.accuracy_m ?? null,
      speed: live.speed_kmh ?? null,
      timestamp: live.recorded_at,
      is_stale: false,
      age_seconds: 0,
      // Fase 7.5: preserva a distância do dia vinda do backend no ponto ao vivo.
      today_distance_km: pointsById.get(live.driver_id)?.today_distance_km,
    })
  }
  const mapPoints: DriverMapPoint[] = [...pointsById.values()]

  // Fase 7.1: ETA + linha tracejada até o endereço da primeira entrega em rota.
  const activeDelivery =
    deliveries.find((d) => ['ASSIGNED', 'DISPATCHED', 'EN_ROUTE'].includes(d.status)) ?? null
  const { data: eta } = useDeliveryEta(activeDelivery?.id ?? null)
  const destination = eta
    ? {
        latitude: eta.destination.latitude,
        longitude: eta.destination.longitude,
        etaLabel: formatEta(eta.eta_seconds),
      }
    : undefined

  const handleCreateDelivery = async () => {
    if (!newDelivery.order_id || !newDelivery.customer_codigo || !newDelivery.customer_name) return
    try {
      await createDelivery.mutateAsync({
        order_id: newDelivery.order_id,
        customer_codigo: newDelivery.customer_codigo,
        customer_name: newDelivery.customer_name,
        notes: newDelivery.notes || undefined,
      })
      setShowCreateForm(false)
      setNewDelivery({ order_id: '', customer_codigo: '', customer_name: '', notes: '' })
    } catch {
      // error handled by mutation
    }
  }

  const handleAssignDriver = async (deliveryId: string) => {
    if (!selectedDriver) return
    try {
      await assignDelivery.mutateAsync({ id: deliveryId, driver_id: selectedDriver })
      setAssigningId(null)
      setSelectedDriver('')
    } catch {
      // error handled by mutation
    }
  }

  const handleStatusChange = async (deliveryId: string, newStatus: string) => {
    // Confirmation for destructive actions
    if (newStatus === 'CANCELLED' || newStatus === 'FAILED') {
      const label = newStatus === 'CANCELLED' ? 'cancelar' : 'marcar como falha'
      if (!window.confirm(`Deseja ${label} esta entrega?`)) return
    }

    if (newStatus === 'FAILED') {
      const reason = prompt('Motivo da falha:', 'OTHER')
      if (reason === null) return // cancelled prompt
      await updateStatus.mutateAsync({
        id: deliveryId,
        status: newStatus,
        failure_reason: reason || 'OTHER',
      })
    } else {
      await updateStatus.mutateAsync({ id: deliveryId, status: newStatus })
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <ErrorState
        message="Não foi possível carregar as entregas."
        onRetry={() => refetch()}
      />
    )
  }

  return (
    <Page>
      <PageHeader>
        <PageTitle subtitle={`${deliveries.length} entrega${deliveries.length !== 1 ? 's' : ''}`}>Entregas</PageTitle>
        <PageActions>
          <Button onClick={() => refetch()} variant="outline">
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => setShowCreateForm(!showCreateForm)}>
            <Plus className="h-4 w-4" />
            Nova Entrega
          </Button>
        </PageActions>
      </PageHeader>

      {/* Create Delivery Form */}
      {showCreateForm && (
        <Card>
          <CardHeader>
            <CardTitle>Criar Entrega</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">ID do Pedido *</label>
                <Input
                  value={newDelivery.order_id}
                  onChange={(e) => setNewDelivery({ ...newDelivery, order_id: e.target.value })}
                  placeholder="Código do pedido"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Código do Cliente *</label>
                <Input
                  value={newDelivery.customer_codigo}
                  onChange={(e) => setNewDelivery({ ...newDelivery, customer_codigo: e.target.value })}
                  placeholder="Código do cliente"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Nome do Cliente *</label>
                <Input
                  value={newDelivery.customer_name}
                  onChange={(e) => setNewDelivery({ ...newDelivery, customer_name: e.target.value })}
                  placeholder="Nome do cliente"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Observações</label>
                <Input
                  value={newDelivery.notes}
                  onChange={(e) => setNewDelivery({ ...newDelivery, notes: e.target.value })}
                  placeholder="Opcional"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreateDelivery} disabled={createDelivery.isPending}>
                {createDelivery.isPending ? 'Criando...' : 'Criar Entrega'}
              </Button>
              <Button variant="ghost" onClick={() => setShowCreateForm(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Summary Stats */}
      {summary && (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <StatCard title="Total Entregas" value={summary.deliveries.total} icon={Package} />
            <StatCard title="Motoristas Disponíveis" value={`${summary.drivers.available}/${summary.drivers.total}`} icon={Truck} />
            <StatCard title="Pendentes" value={summary.deliveries.by_status?.PENDING ?? 0} icon={Clock} />
            <StatCard title="Em Rota" value={summary.deliveries.by_status?.EN_ROUTE ?? 0} icon={Truck} />
          </div>

          {/* Fase 7.3: alertas operacionais (parado/desviado) vindos do barramento */}
          {alerts.length > 0 && (
            <div className="space-y-2">
              {alerts.map((alert, index) => (
                <Alert
                  key={`${alert.driver_id}-${alert.kind}-${index}`}
                  variant={alert.kind === 'DEVIATED' ? 'error' : 'default'}
                  title={alert.kind === 'DEVIATED' ? 'Entregador desviado' : 'Entregador parado'}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4" />
                      {describeAlert(alert)}
                    </span>
                    <button
                      type="button"
                      className="text-xs underline"
                      onClick={() => dismissAlert(index)}
                    >
                      dispensar
                    </button>
                  </div>
                </Alert>
              ))}
            </div>
          )}

          {/* F1b/F6: mapa do operador — posição + trajeto ao vivo (WebSocket) */}
          <Card>
            <CardHeader><CardTitle>Mapa de Entregadores</CardTitle></CardHeader>
            <CardContent>
              <DriverMap
                points={mapPoints}
                trails={pointsByDriver}
                destination={destination}
                className="h-80"
              />
            </CardContent>
          </Card>
        </>
      )}

      {/* Status Filters */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant={statusFilter === '' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setStatusFilter('')}
        >
          Todas
        </Button>
        {Object.entries(STATUS_CONFIG).map(([key, config]) => (
          <Button
            key={key}
            variant={statusFilter === key ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter(key)}
          >
            {config.label}
          </Button>
        ))}
      </div>

      {/* Delivery List */}
      {deliveries.length === 0 ? (
        <EmptyState
          icon={Truck}
          title="Nenhuma entrega encontrada"
          description="Crie uma entrega para começar."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Lista de Entregas</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {deliveries.map((delivery) => {
                const statusConfig = (STATUS_CONFIG[delivery.status] ?? STATUS_CONFIG.PENDING)!
                const StatusIcon = statusConfig.icon
                const address = delivery.address
                  ? `${delivery.address.street}, ${delivery.address.number} - ${delivery.address.neighborhood}`
                  : 'Endereço não informado'
                const transitions = VALID_TRANSITIONS[delivery.status] ?? []

                return (
                  <div
                    key={delivery.id}
                    className="rounded-lg border border-border p-4 hover:bg-accent/50 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="rounded-full bg-muted p-2">
                          <StatusIcon className="h-5 w-5" />
                        </div>
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <p className="font-medium text-foreground">{delivery.customer_name}</p>
                            <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
                          </div>
                          <p className="text-sm text-muted-foreground">
                            Pedido: {delivery.order_id} • Cliente: {delivery.customer_codigo}
                          </p>
                          <p className="text-xs text-muted-foreground flex items-center gap-1">
                            <MapPin className="h-3 w-3" />
                            {address}
                          </p>
                          {delivery.driver_id && (
                            <p className="text-xs text-muted-foreground flex items-center gap-1">
                              <UserCog className="h-3 w-3" />
                              Motorista: {delivery.driver_id.slice(0, 8)}...
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="text-right text-sm text-muted-foreground">
                        {delivery.notes && (
                          <p className="text-xs italic max-w-[200px] truncate">{delivery.notes}</p>
                        )}
                        <p className="text-xs mt-1">
                          {new Date(delivery.created_at).toLocaleDateString('pt-BR')}
                        </p>
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex items-center gap-2 pt-2 border-t border-border/50">
                      {/* Assign Driver (only for PENDING) */}
                      {delivery.status === 'PENDING' && !delivery.driver_id && (
                        <div className="flex items-center gap-2">
                          {assigningId === delivery.id ? (
                            <div className="flex items-center gap-2">
                              <select
                                value={selectedDriver}
                                onChange={(e) => setSelectedDriver(e.target.value)}
                                className="rounded-md border border-border bg-background px-2 py-1 text-sm"
                                aria-label={`Motorista para a entrega ${delivery.id}`}
                              >
                                <option value="">Selecionar motorista</option>
                                {drivers.filter((d: DeliveryDriverExtended) => d.is_available).map((d: DeliveryDriverExtended) => (
                                  <option key={d.id} value={d.id}>{d.name}</option>
                                ))}
                              </select>
                              <Button
                                size="sm"
                                onClick={() => handleAssignDriver(delivery.id)}
                                disabled={!selectedDriver || assignDelivery.isPending}
                              >
                                Atribuir
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => { setAssigningId(null); setSelectedDriver('') }}>
                                Cancelar
                              </Button>
                              {/* F7: sugere o entregador mais próximo com estoque */}
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={suggestLoading}
                                onClick={async () => {
                                  setSuggestLoading(true)
                                  try {
                                    const res = await driverStockApi.suggest(delivery.id)
                                    setSuggestion(res.data as DispatchSuggestionResponse)
                                    setSuggestingId(delivery.id)
                                    const best = (res.data as DispatchSuggestionResponse)?.recommendations?.[0]
                                    if (best) setSelectedDriver(best.driver_id)
                                  } catch {
                                    setSuggestion(null)
                                  } finally {
                                    setSuggestLoading(false)
                                  }
                                }}
                              >
                                <Sparkles className="h-3 w-3 mr-1" />
                                {suggestLoading ? '...' : 'Sugerir'}
                              </Button>
                            </div>
                          ) : (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setAssigningId(delivery.id)}
                            >
                              <UserCog className="h-3 w-3 mr-1" />
                              Atribuir Motorista
                            </Button>
                          )}
                        </div>
                      )}

                      {/* Status Transitions */}
                      {transitions.length > 0 && (
                        <div className="flex items-center gap-2 ml-auto">
                          {transitions.map((t) => (
                            <Button
                              key={t.status}
                              size="sm"
                              variant={t.status === 'CANCELLED' ? 'destructive' : 'default'}
                              onClick={() => handleStatusChange(delivery.id, t.status)}
                              disabled={updateStatus.isPending}
                            >
                              {t.status === 'DELIVERED' ? (
                                <CheckCircle className="h-3 w-3 mr-1" />
                              ) : t.status === 'EN_ROUTE' ? (
                                <ArrowRight className="h-3 w-3 mr-1" />
                              ) : null}
                              {t.label}
                            </Button>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* F7: sugestão do dispatch — operador confirma (C3) */}
                    {suggestingId === delivery.id && suggestion && (
                      <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm space-y-1" role="status">
                        {suggestion.recommendations.length === 0 ? (
                          <p className="text-destructive">
                            Nenhum entregador elegível ({suggestion.error ?? 'sem estoque disponível'})
                            {suggestion.rejected?.length > 0 && ` — ${suggestion.rejected.length} rejeitado(s)`}
                          </p>
                        ) : (
                          suggestion.recommendations.map((rec) => (
                            <div key={rec.driver_id} className="flex items-start justify-between gap-3">
                              <div>
                                <p className="font-medium">
                                  <Sparkles className="inline h-3 w-3 mr-1 text-amber-500" />
                                  {rec.driver_name} · score {rec.score} · {rec.distance_km} km
                                </p>
                                <ul className="text-xs text-muted-foreground list-disc ml-4">
                                  {rec.explanation.map((e, i) => (
                                    <li key={i}>{e}</li>
                                  ))}
                                </ul>
                              </div>
                              <Badge variant="success">Sugestão</Badge>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </Page>
  )
}
