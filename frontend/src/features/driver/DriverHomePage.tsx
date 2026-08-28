/**
 * Driver Home Page — GasFlow Driver App
 *
 * Shows driver's deliveries with workflow actions.
 * Uses /api/v1/driver/* endpoints.
 * Includes GPS tracking, availability toggle, and delivery detail.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Truck, MapPin, Clock, CheckCircle, XCircle, RefreshCw, LogOut, Package, Pause, Play, Navigation, Phone, AlertTriangle, History, User, ChevronRight } from 'lucide-react'
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

interface DriverProfile {
  driver_id: string
  name: string
  phone: string
  status: string
  active: boolean
  tenant_id: string
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
  const [profile, setProfile] = useState<DriverProfile | null>(null)
  const [driverName, setDriverName] = useState('')
  const [driverStatus, setDriverStatus] = useState('AVAILABLE')
  const [gpsEnabled, setGpsEnabled] = useState(false)
  const [lastGpsUpdate, setLastGpsUpdate] = useState<string | null>(null)
  const [detailDelivery, setDetailDelivery] = useState<Delivery | null>(null)
  const gpsWatchId = useRef<number | null>(null)
  const navigate = useNavigate()

  const token = localStorage.getItem('driver_token')

  const fetchDeliveries = useCallback(async () => {
    if (!token) {
      navigate('/driver/login')
      return
    }
    try {
      const response = await fetch('/api/v1/driver/deliveries', {
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
      const response = await fetch('/api/v1/driver/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setProfile(data)
        setDriverName(data.name || 'Motorista')
        setDriverStatus(data.status || 'AVAILABLE')
      }
    } catch { /* silent */ }
  }, [token])

  // GPS Tracking
  const startGpsTracking = useCallback(() => {
    if (!navigator.geolocation) return
    gpsWatchId.current = navigator.geolocation.watchPosition(
      async (position) => {
        if (!token) return
        try {
          await fetch('/api/v1/driver/location', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
              accuracy: position.coords.accuracy,
              speed: position.coords.speed,
              bearing: position.coords.heading,
            }),
          })
          setLastGpsUpdate(new Date().toLocaleTimeString())
        } catch { /* silent */ }
      },
      () => { /* permission denied */ },
      { enableHighAccuracy: true, maximumAge: 15000, timeout: 10000 }
    )
    setGpsEnabled(true)
  }, [token])

  const stopGpsTracking = useCallback(() => {
    if (gpsWatchId.current !== null) {
      navigator.geolocation.clearWatch(gpsWatchId.current)
      gpsWatchId.current = null
    }
    setGpsEnabled(false)
  }, [])

  // Cleanup GPS on unmount
  useEffect(() => {
    return () => { if (gpsWatchId.current !== null) navigator.geolocation.clearWatch(gpsWatchId.current) }
  }, [])

  // Availability toggle
  const toggleAvailability = useCallback(async () => {
    if (!token) return
    const newStatus = driverStatus === 'AVAILABLE' ? 'PAUSED' : 'AVAILABLE'
    try {
      const response = await fetch('/api/v1/driver/availability', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ status: newStatus }),
      })
      if (response.ok) {
        setDriverStatus(newStatus)
      }
    } catch { /* handled */ }
  }, [token, driverStatus])

  useEffect(() => {
    fetchDeliveries()
    fetchProfile()
    const interval = setInterval(fetchDeliveries, 30000)
    return () => clearInterval(interval)
  }, [fetchDeliveries, fetchProfile])

  const handleAction = async (deliveryId: string, action: string) => {
    if (!token) return
    try {
      const response = await fetch(`/api/v1/driver/deliveries/${deliveryId}/${action}`, {
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
    stopGpsTracking()
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

  // Delivery detail view
  if (detailDelivery) {
    return (
      <div className="space-y-4 p-4">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setDetailDelivery(null)}>
            ← Voltar
          </Button>
          <h1 className="text-lg font-bold">Detalhe da Entrega</h1>
        </div>
        <Card>
          <CardContent className="p-4 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-lg">{detailDelivery.customer_name}</p>
                <p className="text-sm text-muted-foreground">Pedido #{detailDelivery.order_reference}</p>
              </div>
              <Badge variant={STATUS_CONFIG[detailDelivery.status]?.variant || 'default'}>
                {STATUS_CONFIG[detailDelivery.status]?.label || detailDelivery.status}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <MapPin className="h-4 w-4" />
              <span>{detailDelivery.address}</span>
            </div>
            {detailDelivery.scheduled_at && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Clock className="h-4 w-4" />
                <span>Agendado: {new Date(detailDelivery.scheduled_at).toLocaleString('pt-BR')}</span>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              {detailDelivery.status === 'PENDING' && (
                <Button onClick={() => { handleAction(detailDelivery.delivery_id, 'accept'); setDetailDelivery(null) }}>
                  <CheckCircle className="h-4 w-4 mr-1" /> Aceitar
                </Button>
              )}
              {(detailDelivery.status === 'ASSIGNED' || detailDelivery.status === 'DISPATCHED') && (
                <Button onClick={() => { handleAction(detailDelivery.delivery_id, 'start'); setDetailDelivery(null) }}>
                  <Truck className="h-4 w-4 mr-1" /> Iniciar Rota
                </Button>
              )}
              {detailDelivery.status === 'EN_ROUTE' && (
                <>
                  <Button onClick={() => { handleAction(detailDelivery.delivery_id, 'complete'); setDetailDelivery(null) }}>
                    <CheckCircle className="h-4 w-4 mr-1" /> Entregue
                  </Button>
                  <Button variant="destructive" onClick={() => { handleAction(detailDelivery.delivery_id, 'fail'); setDetailDelivery(null) }}>
                    <XCircle className="h-4 w-4 mr-1" /> Falha
                  </Button>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

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

      {/* Status Bar */}
      <Card>
        <CardContent className="p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Badge variant={driverStatus === 'AVAILABLE' ? 'success' : 'secondary'}>
                {driverStatus === 'AVAILABLE' ? '🟢 Disponível' : '⏸️ Pausado'}
              </Badge>
              <span className="text-xs text-muted-foreground">
                GPS: {gpsEnabled ? `✅ ${lastGpsUpdate || 'Ativo'}` : '❌ Desligado'}
              </span>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant={driverStatus === 'AVAILABLE' ? 'outline' : 'default'}
                onClick={toggleAvailability}
              >
                {driverStatus === 'AVAILABLE' ? <Pause className="h-4 w-4 mr-1" /> : <Play className="h-4 w-4 mr-1" />}
                {driverStatus === 'AVAILABLE' ? 'Pausar' : 'Retomar'}
              </Button>
              {!gpsEnabled ? (
                <Button size="sm" onClick={startGpsTracking}>
                  <Navigation className="h-4 w-4 mr-1" /> GPS
                </Button>
              ) : (
                <Button size="sm" variant="outline" onClick={stopGpsTracking}>
                  <XCircle className="h-4 w-4 mr-1" /> GPS Off
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

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
            <div key={delivery.delivery_id} onClick={() => setDetailDelivery(delivery)} className="cursor-pointer">
              <DeliveryCard delivery={delivery} onAction={handleAction} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
