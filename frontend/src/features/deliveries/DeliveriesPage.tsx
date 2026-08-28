import { useState, useEffect, useCallback } from 'react'
import { Truck, RefreshCw, Package, MapPin, Clock, CheckCircle, XCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { StatCard } from '@/components/ui/StatCard'
import { apiClient } from '@/lib/api/client'

interface Delivery {
  id: string
  order_id: string
  tenant_id: string
  customer_codigo: string
  customer_name: string
  address?: {
    street: string
    number: string
    neighborhood: string
    city: string
  }
  status: string
  driver_id?: string
  notes: string
  created_at: string
}

interface Driver {
  id: string
  name: string
  phone: string
  status: string
  is_available: boolean
}

interface DispatchSummary {
  deliveries: { total: number; by_status: Record<string, number> }
  drivers: { total: number; available: number }
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
}

export function DeliveriesPage() {
  const [deliveries, setDeliveries] = useState<Delivery[]>([])
  const [_drivers, setDrivers] = useState<Driver[]>([])
  const [summary, setSummary] = useState<DispatchSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const [delRes, driverRes, summaryRes] = await Promise.allSettled([
        apiClient.get('/delivery/deliveries', { params: statusFilter ? { status: statusFilter } : {} }),
        apiClient.get('/delivery/drivers'),
        apiClient.get('/delivery/dispatch/summary'),
      ])

      if (delRes.status === 'fulfilled') setDeliveries(delRes.value.data.deliveries || [])
      if (driverRes.status === 'fulfilled') setDrivers(driverRes.value.data.drivers || [])
      if (summaryRes.status === 'fulfilled') setSummary(summaryRes.value.data)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) {
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
        onRetry={fetchData}
      />
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Entregas</h1>
          <p className="text-muted-foreground">
            {deliveries.length} entrega{deliveries.length !== 1 ? 's' : ''}
          </p>
        </div>
        <Button onClick={fetchData} variant="outline">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Summary Stats */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-4">
          <StatCard
            title="Total Entregas"
            value={summary.deliveries.total}
            icon={Package}
          />
          <StatCard
            title="Motoristas Disponíveis"
            value={`${summary.drivers.available}/${summary.drivers.total}`}
            icon={Truck}
          />
          <StatCard
            title="Pendentes"
            value={summary.deliveries.by_status?.PENDING ?? 0}
            icon={Clock}
          />
          <StatCard
            title="Em Rota"
            value={summary.deliveries.by_status?.EN_ROUTE ?? 0}
            icon={Truck}
          />
        </div>
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
          description="As entregas aparecerão aqui quando forem criadas."
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

                return (
                  <div
                    key={delivery.id}
                    className="flex items-center justify-between rounded-lg border border-border p-4 hover:bg-accent/50"
                  >
                    <div className="flex items-center gap-4">
                      <div className="rounded-full bg-muted p-2">
                        <StatusIcon className="h-5 w-5" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-foreground">
                            {delivery.customer_name}
                          </p>
                          <Badge variant={statusConfig.variant}>
                            {statusConfig.label}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Pedido: {delivery.order_id} • Cliente: {delivery.customer_codigo}
                        </p>
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <MapPin className="h-3 w-3" />
                          {address}
                        </p>
                      </div>
                    </div>
                    <div className="text-right text-sm text-muted-foreground">
                      {delivery.driver_id && (
                        <p>Motorista: {delivery.driver_id.slice(0, 8)}...</p>
                      )}
                      {delivery.notes && (
                        <p className="text-xs italic max-w-[200px] truncate">{delivery.notes}</p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
