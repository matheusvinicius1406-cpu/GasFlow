import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ShoppingCart, Plus, Search, Printer } from 'lucide-react'
import { useOrders } from '@/lib/api/hooks'
import { apiClient } from '@/lib/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'
import { useToast } from '@/components/ui/Toast'
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
  const [printingOrder, setPrintingOrder] = useState<string | null>(null)
  const toast = useToast()

  const { data: orders, isLoading, error, refetch } = useOrders(
    statusFilter === 'all' ? undefined : statusFilter
  )

  const handlePrint = async (orderId: string) => {
    setPrintingOrder(orderId)
    try {
      await apiClient.post('/printer/print', { order_id: orderId })
      toast.success('Pedido enviado para impressão', `#${orderId}`)
    } catch {
      toast.error('Falha ao imprimir', `Verifique a impressora e tente novamente (#${orderId}).`)
    } finally {
      setPrintingOrder(null)
    }
  }

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
    <Page>
      <PageHeader>
        <PageTitle subtitle={`${orders?.length ?? 0} pedidos`}>Pedidos</PageTitle>
        <PageActions>
          <Link to="/orders/new">
            <Button>
              <Plus className="h-4 w-4" />
              Novo Pedido
            </Button>
          </Link>
        </PageActions>
      </PageHeader>

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
                <div
                  key={order.codigo}
                  className="flex items-center justify-between rounded-lg border border-border p-4 transition-colors hover:bg-accent/50"
                >
                  <Link to={`/orders/${order.codigo}`} className="flex-1">
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
                  </Link>
                  <div className="flex items-center gap-3">
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
                    <Button
                      variant="outline"
                      size="sm"
                      aria-label={`Imprimir pedido ${order.codigo}`}
                      disabled={printingOrder === order.codigo}
                      onClick={() => handlePrint(order.codigo)}
                    >
                      <Printer className="h-4 w-4" />
                      {printingOrder === order.codigo ? 'Imprimindo...' : 'Imprimir'}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </Page>
  )
}
