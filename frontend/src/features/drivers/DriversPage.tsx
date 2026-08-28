import { useState, useEffect } from 'react'
import { UserCog, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { apiClient } from '@/lib/api/client'
import type { DeliveryDriver } from '@/types'

export function DriversPage() {
  const [drivers, setDrivers] = useState<DeliveryDriver[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchDrivers = async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await apiClient.get('/delivery-drivers/')
      setDrivers(data)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDrivers()
  }, [])

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
        message="Não foi possível carregar os motoristas."
        onRetry={fetchDrivers}
      />
    )
  }

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
          <Button onClick={fetchDrivers} variant="outline">
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button>
            <UserCog className="h-4 w-4" />
            Novo Motorista
          </Button>
        </div>
      </div>

      {drivers.length === 0 ? (
        <EmptyState
          icon={UserCog}
          title="Nenhum motorista cadastrado"
          description="Comece cadastrando seu primeiro motorista."
          action={
            <Button>
              <UserCog className="h-4 w-4" />
              Cadastrar Motorista
            </Button>
          }
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Lista de Motoristas</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {drivers.map((driver) => (
                <div
                  key={driver.codigo}
                  className="flex items-center justify-between rounded-lg border border-border p-4 hover:bg-accent/50"
                >
                  <div className="space-y-1">
                    <p className="font-medium text-foreground">{driver.nome}</p>
                    <p className="text-sm text-muted-foreground">
                      Código: {driver.codigo}
                      {driver.placa && ` • Placa: ${driver.placa}`}
                    </p>
                    <p className="text-xs text-muted-foreground">{driver.telefone}</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <Badge variant={driver.ativo ? 'success' : 'secondary'}>
                      {driver.ativo ? 'Ativo' : 'Inativo'}
                    </Badge>
                    <Button variant="ghost" size="sm">
                      Ver detalhes
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
