import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { UserCog, RefreshCw, MapPin, Truck, CheckCircle, Pause, XCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { StatCard } from '@/components/ui/StatCard'
import { apiClient } from '@/lib/api/client'
import type { DeliveryDriver } from '@/types'

interface DriverWithLocation extends DeliveryDriver {
  status?: string
  vehicle_id?: string
  location?: {
    lat: number
    lng: number
    timestamp: string
    is_stale: boolean
    age_seconds?: number
  }
}

type StatusConfigEntry = { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' | 'default'; icon: typeof Truck }

const STATUS_CONFIG: Record<string, StatusConfigEntry> = {
  AVAILABLE: { label: 'Disponível', variant: 'success', icon: CheckCircle },
  BUSY: { label: 'Ocupado', variant: 'warning', icon: Truck },
  PAUSED: { label: 'Pausado', variant: 'secondary', icon: Pause },
  OFFLINE: { label: 'Offline', variant: 'secondary', icon: XCircle },
  UNAVAILABLE: { label: 'Indisponível', variant: 'destructive', icon: XCircle },
}

const DEFAULT_STATUS_CONFIG: StatusConfigEntry = { label: 'Desconhecido', variant: 'secondary', icon: Truck }

export function DriversPage() {
  const [drivers, setDrivers] = useState<DriverWithLocation[]>([])
  const [locations, setLocations] = useState<Record<string, { lat: number; lng: number; timestamp: string; is_stale: boolean; age_seconds?: number }>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const [driversRes, locationsRes] = await Promise.allSettled([
        apiClient.get('/delivery-drivers/'),
        apiClient.get('/delivery/locations'),
      ])

      if (driversRes.status === 'fulfilled') {
        setDrivers(driversRes.value.data)
      }
      if (locationsRes.status === 'fulfilled') {
        const locs = locationsRes.value.data?.locations || []
        const locMap: Record<string, typeof locations[string]> = {}
        for (const loc of locs) {
          locMap[loc.driver_id] = loc
        }
        setLocations(locMap)
      }
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

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
      <ErrorState message="Não foi possível carregar os motoristas." onRetry={fetchData} />
    )
  }

  const activeCount = drivers.filter(d => d.status && d.status !== 'OFFLINE' && d.status !== 'INACTIVE').length
  const availableCount = drivers.filter(d => d.status === 'AVAILABLE').length
  const onlineWithGPS = drivers.filter(d => locations[d.codigo]?.is_stale === false).length

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Motoristas</h1>
          <p className="text-muted-foreground">
            {drivers.length} motorista{drivers.length !== 1 ? 's' : ''} cadastrado{drivers.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={fetchData} variant="outline"><RefreshCw className="h-4 w-4" /></Button>
          <Link to="/drivers/new">
            <Button><UserCog className="h-4 w-4" /> Novo Motorista</Button>
          </Link>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard title="Total" value={drivers.length} icon={UserCog} />
        <StatCard title="Ativos" value={activeCount} icon={CheckCircle} />
        <StatCard title="Disponíveis" value={availableCount} icon={Truck} />
        <StatCard title="Com GPS" value={onlineWithGPS} icon={MapPin} />
      </div>

      {drivers.length === 0 ? (
        <EmptyState
          icon={UserCog}
          title="Nenhum motorista cadastrado"
          description="Comece cadastrando seu primeiro motorista."
          action={<Link to="/drivers/new"><Button><UserCog className="h-4 w-4" /> Cadastrar Motorista</Button></Link>}
        />
      ) : (
        <Card>
          <CardHeader><CardTitle>Lista de Motoristas</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              {drivers.map((driver) => {
                const statusConfig = STATUS_CONFIG[driver.status || 'AVAILABLE'] ?? DEFAULT_STATUS_CONFIG
                const StatusIcon = statusConfig.icon
                const loc = locations[driver.codigo]
                return (
                  <div key={driver.codigo} className="flex items-center justify-between rounded-lg border border-border p-4 hover:bg-accent/50">
                    <div className="flex items-center gap-4">
                      <div className="rounded-full bg-muted p-2">
                        <StatusIcon className="h-5 w-5" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-foreground">{driver.nome}</p>
                          <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Código: {driver.codigo}
                          {driver.placa && ` • Placa: ${driver.placa}`}
                        </p>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <span>{driver.telefone}</span>
                          {loc && (
                            <span className="flex items-center gap-1">
                              <MapPin className="h-3 w-3" />
                              GPS: {loc.is_stale ? 'Stale' : 'Ativo'}
                              {loc.age_seconds != null && loc.age_seconds > 0 && ` (${Math.floor(loc.age_seconds / 60)}min)`}
                            </span>
                          )}
                          {!loc && (
                            <span className="flex items-center gap-1 text-muted-foreground/50">
                              <MapPin className="h-3 w-3" /> Sem GPS
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Link to={`/drivers/${driver.codigo}/edit`}>
                        <Button variant="ghost" size="sm">Editar</Button>
                      </Link>
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
