import { ShoppingCart, Users, Package, Truck, DollarSign, AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { StatCard } from '@/components/ui/StatCard'
import { StatusBadge } from '@/components/ui/StatusBadge'

// Mock data for development - will be replaced with real API calls
const mockStats = {
  totalOrders: 47,
  pendingOrders: 12,
  totalRevenue: 8450.0,
  totalClients: 156,
  totalProducts: 8,
  activeDrivers: 3,
}

const mockRecentOrders = [
  { codigo: '000047', client_codigo: '000012', product: 'P13', quantity: 2, value: 179.8, status: 'PENDING', created_at: '2026-08-26T10:30:00' },
  { codigo: '000046', client_codigo: '000008', product: 'AGUA_20L', quantity: 3, value: 45.0, status: 'DELIVERED', created_at: '2026-08-26T09:15:00' },
  { codigo: '000045', client_codigo: '000023', product: 'P13', quantity: 1, value: 89.9, status: 'DELIVERING', created_at: '2026-08-26T08:45:00' },
  { codigo: '000044', client_codigo: '000005', product: 'P13', quantity: 4, value: 359.6, status: 'CONFIRMED', created_at: '2026-08-25T18:20:00' },
  { codigo: '000043', client_codigo: '000019', product: 'AGUA_20L', quantity: 2, value: 30.0, status: 'CANCELLED', created_at: '2026-08-25T16:00:00' },
]

const mockAlerts = [
  { id: 1, message: 'Estoque de P13 abaixo do mínimo', type: 'warning' as const },
  { id: 2, message: '3 pedidos aguardando confirmação', type: 'info' as const },
  { id: 3, message: 'Motorista João não entregar hoje', type: 'error' as const },
]

export function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-muted-foreground">Visão geral da operação</p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Pedidos Hoje"
          value={mockStats.totalOrders}
          icon={ShoppingCart}
          trend={{ value: 12, isPositive: true }}
        />
        <StatCard
          title="Faturamento"
          value={`R$ ${mockStats.totalRevenue.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`}
          icon={DollarSign}
          trend={{ value: 8, isPositive: true }}
        />
        <StatCard
          title="Clientes Ativos"
          value={mockStats.totalClients}
          icon={Users}
          trend={{ value: 3, isPositive: true }}
        />
        <StatCard
          title="Em Entrega"
          value={mockStats.pendingOrders}
          icon={Truck}
          description={`${mockStats.activeDrivers} motoristas ativos`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent Orders */}
        <Card>
          <CardHeader>
            <CardTitle>Pedidos Recentes</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {mockRecentOrders.map((order) => (
                <div
                  key={order.codigo}
                  className="flex items-center justify-between rounded-lg border border-border p-3"
                >
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-foreground">
                      Pedido #{order.codigo}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Cliente {order.client_codigo} • {order.product} x{order.quantity}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <p className="text-sm font-medium text-foreground">
                      R$ {order.value.toFixed(2)}
                    </p>
                    <StatusBadge status={order.status} />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Alerts */}
        <Card>
          <CardHeader>
            <CardTitle>Alertas</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {mockAlerts.map((alert) => (
                <div
                  key={alert.id}
                  className="flex items-start gap-3 rounded-lg border border-border p-3"
                >
                  <AlertTriangle
                    className={`h-5 w-5 ${
                      alert.type === 'warning'
                        ? 'text-warning'
                        : alert.type === 'error'
                        ? 'text-destructive'
                        : 'text-info'
                    }`}
                  />
                  <p className="text-sm text-foreground">{alert.message}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Produtos</p>
                <p className="text-2xl font-bold text-foreground">{mockStats.totalProducts}</p>
              </div>
              <Package className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Motoristas Ativos</p>
                <p className="text-2xl font-bold text-foreground">{mockStats.activeDrivers}</p>
              </div>
              <Truck className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Ticket Médio</p>
                <p className="text-2xl font-bold text-foreground">
                  R$ {(mockStats.totalRevenue / mockStats.totalOrders).toFixed(2)}
                </p>
              </div>
              <DollarSign className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
