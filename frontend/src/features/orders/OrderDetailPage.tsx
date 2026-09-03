import { useState, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, MapPin, CreditCard, Package, CheckCircle, DollarSign, History } from 'lucide-react'
import { useOrder, useUpdateOrderStatus, useRegisterPayment, useReceivables, useOrderPayments } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
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

const paymentMethodLabels: Record<string, string> = {
  CASH: 'Dinheiro',
  PIX: 'PIX',
  CARD: 'Cartão',
  TRANSFER: 'Transferência',
  OTHER: 'Outro',
}

export function OrderDetailPage() {
  const { codigo } = useParams<{ codigo: string }>()
  const { data: order, isLoading, error, refetch } = useOrder(codigo ?? '')
  const updateStatus = useUpdateOrderStatus()
  const registerPayment = useRegisterPayment()

  // Fetch receivable for this specific order to get remaining_amount
  const { data: receivablesData } = useReceivables({ order_codigo: codigo })
  const receivable = receivablesData?.items?.[0]
  const remainingAmount = receivable?.remaining_amount ?? (order?.total ?? 0)

  // Fetch payment history for this order
  const { data: paymentsData } = useOrderPayments(codigo ?? '')
  const payments = paymentsData?.items ?? []

  // Payment form state
  const [showPaymentForm, setShowPaymentForm] = useState(false)
  const [paymentAmount, setPaymentAmount] = useState('')
  const [paymentMethod, setPaymentMethod] = useState('CASH')
  const [paymentNotes, setPaymentNotes] = useState('')
  const [paymentError, setPaymentError] = useState('')
  // Stable idempotency key per payment attempt — generated when form opens
  const idempotencyKeyRef = useRef<string>('')

  const handleStatusChange = async (newStatus: string) => {
    if (!order) return
    const confirmMessage = newStatus === 'CANCELLED'
      ? 'Deseja cancelar este pedido?'
      : `Deseja alterar o status para ${newStatus}?`

    if (window.confirm(confirmMessage)) {
      await updateStatus.mutateAsync({ codigo: order.codigo, status: newStatus })
    }
  }

  const handleRegisterPayment = async () => {
    if (!order) return
    const amount = parseFloat(paymentAmount)
    if (isNaN(amount) || amount <= 0) {
      setPaymentError('Valor deve ser maior que zero.')
      return
    }
    if (amount > remainingAmount) {
      setPaymentError(
        `Valor não pode exceder o saldo restante (${formatCurrency(remainingAmount)}).`
      )
      return
    }
    setPaymentError('')
    try {
      await registerPayment.mutateAsync({
        order_codigo: order.codigo,
        amount,
        method: paymentMethod,
        idempotency_key: idempotencyKeyRef.current,
        notes: paymentNotes || undefined,
      })
      setShowPaymentForm(false)
      setPaymentAmount('')
      setPaymentNotes('')
      refetch()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setPaymentError(msg || 'Erro ao registrar pagamento.')
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
  const paidAmount = receivable?.paid_amount ?? 0

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
          <CardContent className="space-y-3">
            {/* Financial summary */}
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Total</span>
              <span className="text-sm font-bold text-foreground">{formatCurrency(order.total ?? 0)}</span>
            </div>
            {paidAmount > 0 && (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Já pago</span>
                  <span className="text-sm font-medium text-success">{formatCurrency(paidAmount)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Restante</span>
                  <span className="text-sm font-bold text-foreground">{formatCurrency(remainingAmount)}</span>
                </div>
              </>
            )}
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

            {/* Register Payment Button */}
            {order.payment_status !== 'PAID' && order.status !== 'CANCELLED' && remainingAmount > 0 && (
              <>
                {!showPaymentForm ? (
                  <Button
                    onClick={() => {
                      setShowPaymentForm(true)
                      setPaymentAmount(String(remainingAmount))
                      // Generate stable idempotency key for this payment attempt
                      idempotencyKeyRef.current = `pay-${order.codigo}-${Date.now()}`
                    }}
                    className="w-full"
                    size="sm"
                  >
                    <DollarSign className="h-4 w-4" />
                    Registrar Pagamento
                  </Button>
                ) : (
                  <div className="space-y-3 rounded-lg border border-border p-3">
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-foreground">
                        Valor (R$) — Saldo restante: {formatCurrency(remainingAmount)}
                      </label>
                      <Input
                        type="number"
                        min="0.01"
                        max={remainingAmount}
                        step="0.01"
                        value={paymentAmount}
                        onChange={(e) => setPaymentAmount(e.target.value)}
                        placeholder="0,00"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-foreground">Método</label>
                      <select
                        value={paymentMethod}
                        onChange={(e) => setPaymentMethod(e.target.value)}
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
                      >
                        <option value="CASH">Dinheiro</option>
                        <option value="PIX">PIX</option>
                        <option value="CARD">Cartão</option>
                        <option value="TRANSFER">Transferência</option>
                        <option value="OTHER">Outro</option>
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-foreground">Observações</label>
                      <Input
                        value={paymentNotes}
                        onChange={(e) => setPaymentNotes(e.target.value)}
                        placeholder="Opcional"
                      />
                    </div>
                    {paymentError && (
                      <p className="text-sm text-destructive">{paymentError}</p>
                    )}
                    <div className="flex gap-2">
                      <Button
                        onClick={handleRegisterPayment}
                        disabled={registerPayment.isPending || !paymentAmount}
                        size="sm"
                      >
                        {registerPayment.isPending ? 'Registrando...' : 'Confirmar Pagamento'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setShowPaymentForm(false)
                          setPaymentError('')
                        }}
                      >
                        Cancelar
                      </Button>
                    </div>
                  </div>
                )}
              </>
            )}

            {order.payment_status === 'PAID' && (
              <div className="flex items-center gap-2 rounded-md bg-success/10 p-2">
                <CheckCircle className="h-4 w-4 text-success" />
                <span className="text-sm text-success font-medium">Pedido pago</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Payment History */}
      {payments.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <History className="h-5 w-5" />
              Histórico de Pagamentos ({payments.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {payments.map((payment) => (
                <div
                  key={payment.id}
                  className="flex items-center justify-between rounded-lg border border-border p-3"
                >
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-foreground">
                      {formatCurrency(payment.amount)} — {paymentMethodLabels[payment.method] ?? payment.method}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {payment.paid_at ? formatDate(payment.paid_at) : formatDate(payment.created_at)}
                      {payment.notes && ` — ${payment.notes}`}
                    </p>
                  </div>
                  <Badge
                    variant={
                      payment.status === 'PAID'
                        ? 'success'
                        : payment.status === 'REFUNDED'
                        ? 'destructive'
                        : 'secondary'
                    }
                  >
                    {paymentStatusLabels[payment.status] ?? payment.status}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

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
