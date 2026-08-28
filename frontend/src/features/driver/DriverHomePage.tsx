/**
 * Driver Home Page — GasFlow Driver App
 *
 * Shows driver's deliveries with workflow actions.
 * Uses /api/driver/v1/deliveries endpoint.
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Truck, MapPin, Clock, CheckCircle, XCircle, RefreshCw, LogOut, Package } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'

interface Delivery {
  delivery_id: string
  order_reference: string
  customer_name: string
  address: string
  status: string
  scheduled_at: string | null
  version: number
}

const STATUS_CONFIG: Record<string, { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' | 'default'; icon: typeof Truck }> = {
  PENDING: { label: 'Pendente', variant: 'secondary', icon: Clock },
  ASSIGNED: { label: 'Atribuída', variant: 'default', icon: Package },
  DISPATCHED: { label: 'Despachada', variant: 'default', icon: Truck },
  EN_ROUTE: { label: 'Em Rota', variant: 'warning', icon: Truck },
  ARRIVED: { label: 'Chegou', variant: 'warning', icon: MapPin },
  DELIVERED: { label: 'Entregue', variant: 'success', icon: CheckCircle },
  FAILED: { label: 'Falhou', variant: 'destructive', icon: XCircle },
}

function DeliveryCard({ delivery, onAction }: { delivery: Delivery; onAction: (id: string, action: string) => void }) {
  const defaultConfig = { label: delivery.status, variant: 'secondary' as const, icon: Package }
  const config = STATUS_CONFIG[delivery.status] || defaultConfig
  const Icon = config.icon

  return (
    <Card className="mb-3">
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-muted p-2">
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <p className="font-medium">{delivery.customer_name}</p>
              <p className="text-sm text-muted-foreground">Pedido #{delivery.order_reference}</p>
            </div>
          </div>
          <Badge variant={config.variant as 'success' | 'warning' | 'destructive' | 'secondary' | 'default'}>{config.label}</Badge>
        </div>

        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3">
          <MapPin className="h-4 w-4" />
          <span>{delivery.address}</span>
        </div>

        <div className="flex gap-2">
          {delivery.status === 'PENDING' && (
            <Button size="sm" onClick={() => onAction(delivery.delivery_id, 'accept')}>
              <CheckCircle className="h-4 w-4 mr-1" /> Aceitar
            </Button>
          )}
          {(delivery.status === 'ASSIGNED' || delivery.status === 'DISPATCHED') && (
            <Button size="sm" onClick={() => onAction(delivery.delivery_id, 'start')}>
              <Truck className="h-4 w-4 mr-1" /> Iniciar Rota
            </Button>
          )}
          {delivery.status === 'EN_ROUTE' && (
            <>
              <Button size="sm" onClick={() => onAction(delivery.delivery_id, 'complete')}>
                <CheckCircle className="h-4 w-4 mr-1" /> Entregue
              </Button>
              <Button size="sm" variant="destructive" onClick={() => onAction(delivery.delivery_id, 'fail')}>
                <XCircle className="h-4 w-4 mr-1" /> Falha
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function DriverHomePage() {
  const [deliveries, setDeliveries] = useState<Delivery[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [driverName, setDriverName] = useState('')
  const navigate = useNavigate()

  const token = localStorage.getItem('driver_token')

  const fetchDeliveries = useCallback(async () => {
    if (!token) {
      navigate('/driver/login')
      return
    }

    try {
      const response = await fetch('/api/driver/v1/deliveries', {
        headers: { Authorization: `Bearer ${token}` },
      })

      if (response.status === 401) {
        localStorage.removeItem('driver_token')
        navigate('/driver/login')
        return
      }

      const data = await response.json()
      setDeliveries(data.deliveries || [])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [token, navigate])

  const fetchProfile = useCallback(async () => {
    if (!token) return
    try {
      const response = await fetch('/api/driver/v1/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setDriverName(data.name || 'Motorista')
      }
    } catch { /* silent */ }
  }, [token])

  useEffect(() => {
    fetchDeliveries()
    fetchProfile()
    const interval = setInterval(fetchDeliveries, 30000) // Poll every 30s
    return () => clearInterval(interval)
  }, [fetchDeliveries, fetchProfile])

  const handleAction = async (deliveryId: string, action: string) => {
    if (!token) return

    try {
      const response = await fetch(`/api/driver/v1/deliveries/${deliveryId}/${action}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      })

      if (response.ok) {
        fetchDeliveries()
      }
    } catch { /* handled */ }
  }

  const handleLogout = () => {
    localStorage.removeItem('driver_token')
    localStorage.removeItem('driver_id')
    localStorage.removeItem('driver_tenant')
    navigate('/driver/login')
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  const pendingCount = deliveries.filter(d => d.status === 'PENDING').length
  const activeCount = deliveries.filter(d => ['ASSIGNED', 'DISPATCHED', 'EN_ROUTE'].includes(d.status)).length
  const completedCount = deliveries.filter(d => d.status === 'DELIVERED').length

  return (
    <div className="space-y-4 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Olá, {driverName}</h1>
          <p className="text-sm text-muted-foreground">Suas entregas de hoje</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="icon" onClick={fetchDeliveries}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={handleLogout}>
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <CardContent className="p-3 text-center">
            <p className="text-2xl font-bold text-yellow-600">{pendingCount}</p>
            <p className="text-xs text-muted-foreground">Pendentes</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3 text-center">
            <p className="text-2xl font-bold text-blue-600">{activeCount}</p>
            <p className="text-xs text-muted-foreground">Em Rota</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3 text-center">
            <p className="text-2xl font-bold text-green-600">{completedCount}</p>
            <p className="text-xs text-muted-foreground">Entregues</p>
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          Erro ao carregar entregas. Tente novamente.
        </div>
      )}

      {/* Deliveries */}
      {deliveries.length === 0 ? (
        <EmptyState
          icon={Truck}
          title="Nenhuma entrega"
          description="Suas entregas aparecerão aqui quando forem atribuídas."
        />
      ) : (
        <div>
          <h2 className="text-lg font-semibold mb-3">Minhas Entregas</h2>
          {deliveries.map(delivery => (
            <DeliveryCard
              key={delivery.delivery_id}
              delivery={delivery}
              onAction={handleAction}
            />
          ))}
        </div>
      )}
    </div>
  )
}
