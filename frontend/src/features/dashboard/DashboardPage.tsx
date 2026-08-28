import { useState, useEffect } from 'react'
import { ShoppingCart, Users, Package, Truck, DollarSign, AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { StatCard } from '@/components/ui/StatCard'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { apiClient } from '@/lib/api/client'
import { formatDate, formatCurrency } from '@/lib/utils'
import type { Order, Product } from '@/types'

export function DashboardPage() {
  const [stats, setStats] = useState({
    totalOrders: 0,
    pendingOrders: 0,
    totalRevenue: 0,
    totalClients: 0,
    totalProducts: 0,
    activeDrivers: 0,
    totalReceived: 0,
    totalPending: 0,
  })
  const [recentOrders, setRecentOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      try {
        const [ordersRes, clientsRes, productsRes, driversRes, paymentsRes] = await Promise.allSettled([
          apiClient.get('/orders/'),
          apiClient.get('/clients/'),
          apiClient.get('/products/'),
          apiClient.get('/delivery-drivers/'),
          apiClient.get('/payments/summary'),
        ])

        const orders: Order[] = ordersRes.status === 'fulfilled' ? ordersRes.value.data : []
        const clientsData = clientsRes.status === 'fulfilled' ? clientsRes.value.data : { total: 0 }
        const products: Product[] = productsRes.status === 'fulfilled' ? productsRes.value.data : []
        const drivers: unknown[] = driversRes.status === 'fulfilled' ? driversRes.value.data : []

        const totalRevenue = orders
          .filter(o => o.payment_status === 'PAID')
          .reduce((sum, o) => sum + (o.total ?? 0), 0)

        const paymentSummary = paymentsRes.status === 'fulfilled' ? paymentsRes.value.data : {}

        setStats({
          totalOrders: orders.length,
          pendingOrders: orders.filter(o => o.status === 'PENDING').length,
          totalRevenue,
          totalClients: clientsData.total ?? clientsData.length ?? 0,
          totalProducts: products.length,
          activeDrivers: Array.isArray(drivers) ? drivers.length : 0,
          totalReceived: paymentSummary.total_received || 0,
          totalPending: paymentSummary.total_pending || 0,
        })

        setRecentOrders(orders.slice(0, 5))
      } catch {
        // Keep defaults
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-muted-foreground">Visão geral da operação</p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total de Pedidos"
          value={stats.totalOrders}
          icon={ShoppingCart}
        />
        <StatCard
          title="Faturamento"
          value={formatCurrency(stats.totalRevenue)}
          icon={DollarSign}
        />
        <StatCard
          title="Clientes Ativos"
          value={stats.totalClients}
          icon={Users}
        />
        <StatCard
          title="Pendentes"
          value={stats.pendingOrders}
          icon={Truck}
          description={`${stats.activeDrivers} motoristas`}
        />
      </div>

      {/* Payment Stats */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Recebido"
          value={formatCurrency(stats.totalReceived)}
          icon={DollarSign}
          description="Pagamentos confirmados"
        />
        <StatCard
          title="Pendente"
          value={formatCurrency(stats.totalPending)}
          icon={AlertTriangle}
          description="Aguardando pagamento"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent Orders */}
        <Card>
          <CardHeader>
            <CardTitle>Pedidos Recentes</CardTitle>
          </CardHeader>
          <CardContent>
            {recentOrders.length === 0 ? (
              <EmptyState
                icon={ShoppingCart}
                title="Nenhum pedido"
                description="Os pedidos recentes aparecerão aqui."
              />
            ) : (
              <div className="space-y-4">
                {recentOrders.map((order) => (
                  <div
                    key={order.codigo}
                    className="flex items-center justify-between rounded-lg border border-border p-3"
                  >
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-foreground">
                        Pedido #{order.codigo}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Cliente {order.client_codigo} • {formatDate(order.created_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <p className="text-sm font-medium text-foreground">
                        {formatCurrency(order.total)}
                      </p>
                      <StatusBadge status={order.status} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Alerts */}
        <Card>
          <CardHeader>
            <CardTitle>Resumo Rápido</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {stats.pendingOrders > 0 && (
                <div className="flex items-start gap-3 rounded-lg border border-border p-3">
                  <AlertTriangle className="h-5 w-5 text-yellow-500" />
                  <p className="text-sm text-foreground">
                    {stats.pendingOrders} pedido{stats.pendingOrders > 1 ? 's' : ''} aguardando processamento
                  </p>
                </div>
              )}
              {stats.totalClients > 0 && (
                <div className="flex items-start gap-3 rounded-lg border border-border p-3">
                  <Users className="h-5 w-5 text-primary" />
                  <p className="text-sm text-foreground">
                    {stats.totalClients} cliente{stats.totalClients > 1 ? 's' : ''} cadastrado{stats.totalClients > 1 ? 's' : ''}
                  </p>
                </div>
              )}
              {stats.totalProducts > 0 && (
                <div className="flex items-start gap-3 rounded-lg border border-border p-3">
                  <Package className="h-5 w-5 text-blue-500" />
                  <p className="text-sm text-foreground">
                    {stats.totalProducts} produto{stats.totalProducts > 1 ? 's' : ''} cadastrado{stats.totalProducts > 1 ? 's' : ''}
                  </p>
                </div>
              )}
              {stats.pendingOrders === 0 && stats.totalClients === 0 && stats.totalProducts === 0 && (
                <EmptyState
                  icon={Package}
                  title="Sistema vazio"
                  description="Comece cadastrando clientes e produtos."
                />
              )}
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
                <p className="text-2xl font-bold text-foreground">{stats.totalProducts}</p>
              </div>
              <Package className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Motoristas</p>
                <p className="text-2xl font-bold text-foreground">{stats.activeDrivers}</p>
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
                  {stats.totalOrders > 0
                    ? formatCurrency(stats.totalRevenue / stats.totalOrders)
                    : formatCurrency(0)}
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
