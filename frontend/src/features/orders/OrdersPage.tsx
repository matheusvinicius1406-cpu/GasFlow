import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ShoppingCart, Plus, Search } from 'lucide-react'
import { useOrders } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatCurrency, formatDate } from '@/lib/utils'
import type { OrderStatus } from '@/types'

const statusOptions: { value: OrderStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Todos' },
  { value: 'PENDING', label: 'Novo' },
  { value: 'CONFIRMED', label: 'Confirmado' },
  { value: 'PREPARING', label: 'Preparando' },
  { value: 'DELIVERING', label: 'Em entrega' },
  { value: 'DELIVERED', label: 'Entregue' },
  { value: 'CANCELLED', label: 'Cancelado' },
]

const sourceLabels: Record<string, string> = {
  WHATSAPP: 'WhatsApp',
  PHONE: 'Telefone',
  WEB: 'Web',
  COUNTER: 'Balcão',
  MANUAL: 'Manual',
  API: 'API',
}

export function OrdersPage() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<OrderStatus | 'all'>('all')

  const { data: orders, isLoading, error, refetch } = useOrders(
    statusFilter === 'all' ? undefined : statusFilter
  )

  const filteredOrders = (orders ?? []).filter((order) => {
    if (!search) return true
    const searchLower = search.toLowerCase()
    return (
      order.codigo.includes(search) ||
      order.client_codigo.includes(search) ||
      order.address_snapshot.toLowerCase().includes(searchLower)
    )
  })

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
        message="Não foi possível carregar os pedidos."
        onRetry={() => refetch()}
      />
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Pedidos</h1>
          <p className="text-muted-foreground">
            {orders?.length ?? 0} pedidos
          </p>
        </div>
        <Link to="/orders/new">
          <Button>
            <Plus className="h-4 w-4" />
            Novo Pedido
          </Button>
        </Link>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Buscar por código ou cliente..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {statusOptions.map((option) => (
            <Button
              key={option.value}
              variant={statusFilter === option.value ? 'default' : 'outline'}
              size="sm"
              onClick={() => setStatusFilter(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Order List */}
      {filteredOrders.length === 0 ? (
        <EmptyState
          icon={ShoppingCart}
          title={search ? 'Nenhum pedido encontrado' : 'Nenhum pedido'}
          description={
            search
              ? 'Nenhum pedido corresponde aos filtros aplicados.'
              : 'Comece criando seu primeiro pedido.'
          }
          action={
            !search ? (
              <Link to="/orders/new">
                <Button>
                  <Plus className="h-4 w-4" />
                  Criar Pedido
                </Button>
              </Link>
            ) : undefined
          }
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Lista de Pedidos</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {filteredOrders.map((order) => (
                <Link
                  key={order.codigo}
                  to={`/orders/${order.codigo}`}
                  className="flex items-center justify-between rounded-lg border border-border p-4 transition-colors hover:bg-accent/50"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-foreground">#{order.codigo}</p>
                      <StatusBadge status={order.status} />
                      <Badge variant="outline" className="text-xs">
                        {sourceLabels[order.source] ?? order.source}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Cliente: {order.client_codigo}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(order.created_at)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-foreground">
                      {formatCurrency(order.total)}
                    </p>
                    <Badge
                      variant={
                        order.payment_status === 'PAID'
                          ? 'success'
                          : order.payment_status === 'FAILED'
                          ? 'destructive'
                          : 'secondary'
                      }
                      className="text-xs"
                    >
                      {order.payment_status === 'PAID'
                        ? 'Pago'
                        : order.payment_status === 'PENDING'
                        ? 'Pendente'
                        : order.payment_status}
                    </Badge>
                  </div>
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
