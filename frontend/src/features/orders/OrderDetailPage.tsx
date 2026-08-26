import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, MapPin, CreditCard, Package } from 'lucide-react'
import { useOrder, useUpdateOrderStatus } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { formatCurrency, formatDate } from '@/lib/utils'

const statusActions: Record<string, { label: string; next: string; variant: 'default' | 'destructive' }[]> = {
  PENDING: [
    { label: 'Confirmar', next: 'CONFIRMED', variant: 'default' },
    { label: 'Cancelar', next: 'CANCELLED', variant: 'destructive' },
  ],
  CONFIRMED: [
    { label: 'Preparar', next: 'PREPARING', variant: 'default' },
    { label: 'Cancelar', next: 'CANCELLED', variant: 'destructive' },
  ],
  PREPARING: [
    { label: 'Enviar', next: 'DELIVERING', variant: 'default' },
    { label: 'Cancelar', next: 'CANCELLED', variant: 'destructive' },
  ],
  DELIVERING: [
    { label: 'Entregar', next: 'DELIVERED', variant: 'default' },
  ],
}

const paymentStatusLabels: Record<string, string> = {
  PENDING: 'Pendente',
  AUTHORIZED: 'Autorizado',
  PAID: 'Pago',
  FAILED: 'Falhou',
  REFUNDED: 'Reembolsado',
  PARTIAL: 'Parcial',
}

export function OrderDetailPage() {
  const { codigo } = useParams<{ codigo: string }>()
  const { data: order, isLoading, error, refetch } = useOrder(codigo ?? '')
  const updateStatus = useUpdateOrderStatus()

  const handleStatusChange = async (newStatus: string) => {
    if (!order) return
    const confirmMessage = newStatus === 'CANCELLED'
      ? 'Deseja cancelar este pedido?'
      : `Deseja alterar o status para ${newStatus}?`

    if (window.confirm(confirmMessage)) {
      await updateStatus.mutateAsync({ codigo: order.codigo, status: newStatus })
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error || !order) {
    return (
      <ErrorState
        message="Não foi possível carregar os dados do pedido."
        onRetry={() => refetch()}
      />
    )
  }

  const actions = statusActions[order.status] ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <Link
            to="/orders"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-foreground">Pedido #{order.codigo}</h1>
            <StatusBadge status={order.status} />
          </div>
          <p className="text-sm text-muted-foreground">
            Criado em {formatDate(order.created_at)}
          </p>
        </div>
        <div className="flex gap-2">
          {actions.map((action) => (
            <Button
              key={action.next}
              variant={action.variant}
              onClick={() => handleStatusChange(action.next)}
              disabled={updateStatus.isPending}
            >
              {action.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Customer Info */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Package className="h-5 w-5" />
              Cliente
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-medium text-foreground">Código: {order.client_codigo}</p>
          </CardContent>
        </Card>

        {/* Payment Info */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CreditCard className="h-5 w-5" />
              Pagamento
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Status</span>
              <Badge
                variant={
                  order.payment_status === 'PAID'
                    ? 'success'
                    : order.payment_status === 'FAILED'
                    ? 'destructive'
                    : 'secondary'
                }
              >
                {paymentStatusLabels[order.payment_status] ?? order.payment_status}
              </Badge>
            </div>
            {order.payment_method && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Método</span>
                <span className="text-sm font-medium text-foreground">{order.payment_method}</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Address */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MapPin className="h-5 w-5" />
            Endereço de Entrega
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-foreground">{order.address_snapshot}</p>
        </CardContent>
      </Card>

      {/* Items */}
      <Card>
        <CardHeader>
          <CardTitle>Itens do Pedido</CardTitle>
        </CardHeader>
        <CardContent>
          {order.items && order.items.length > 0 ? (
            <div className="space-y-3">
              {order.items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between rounded-lg border border-border p-3"
                >
                  <div>
                    <p className="font-medium text-foreground">{item.product_nome}</p>
                    <p className="text-sm text-muted-foreground">
                      {item.quantity} × {formatCurrency(item.unit_price)}
                    </p>
                  </div>
                  <p className="font-medium text-foreground">
                    {formatCurrency(item.subtotal)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Itens não disponíveis</p>
          )}
        </CardContent>
      </Card>

      {/* Summary */}
      <Card>
        <CardHeader>
          <CardTitle>Resumo</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Subtotal</span>
            <span className="text-sm text-foreground">{formatCurrency(order.subtotal)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Entrega</span>
            <span className="text-sm text-foreground">{formatCurrency(order.delivery_fee)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Desconto</span>
            <span className="text-sm text-foreground">-{formatCurrency(order.discount)}</span>
          </div>
          <div className="border-t border-border pt-2">
            <div className="flex items-center justify-between">
              <span className="font-medium text-foreground">Total</span>
              <span className="text-lg font-bold text-foreground">
                {formatCurrency(order.total)}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Notes */}
      {order.notes && (
        <Card>
          <CardHeader>
            <CardTitle>Observações</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-foreground">{order.notes}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
