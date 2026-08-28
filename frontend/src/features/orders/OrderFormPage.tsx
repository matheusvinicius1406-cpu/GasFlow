import { useState, useEffect } from 'react'
import { useNavigate, Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Plus, Trash2, ShoppingCart } from 'lucide-react'
import { useCustomersLegacy, useProducts, useCreateOrder } from '@/lib/api/hooks'
import { apiClient } from '@/lib/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { formatCurrency } from '@/lib/utils'

interface OrderItemForm {
  product_codigo: string
  quantity: number
}

export function OrderFormPage() {
  const [searchParams] = useSearchParams()
  const preselectedCustomer = searchParams.get('customer') ?? ''

  const [clientCodigo, setClientCodigo] = useState(preselectedCustomer)
  const [items, setItems] = useState<OrderItemForm[]>([
    { product_codigo: '', quantity: 1 },
  ])
  const [deliveryFee, setDeliveryFee] = useState(0)
  const [discount, setDiscount] = useState(0)
  const [paymentMethod, setPaymentMethod] = useState('')
  const [notes, setNotes] = useState('')

  const navigate = useNavigate()
  const { data: customers, isLoading: loadingCustomers } = useCustomersLegacy()
  const [paymentMethods, setPaymentMethods] = useState<{code: string; name: string; payment_type: string}[]>([])

  useEffect(() => {
    apiClient.get('/payments/methods').then(({ data }) => {
      setPaymentMethods((data.methods || []).filter((m: {enabled: boolean}) => m.enabled))
    }).catch(() => {})
  }, [])
  const { data: products, isLoading: loadingProducts } = useProducts()
  const createOrder = useCreateOrder()

  const selectedCustomer = customers?.find((c) => c.codigo === clientCodigo)

  const getProductPrice = (codigo: string): number => {
    const product = products?.find((p) => p.codigo === codigo)
    return product?.preco ?? 0
  }

  const subtotal = items.reduce((acc, item) => {
    const price = getProductPrice(item.product_codigo)
    return acc + price * item.quantity
  }, 0)

  const total = subtotal + deliveryFee - discount

  const addItem = () => {
    setItems([...items, { product_codigo: '', quantity: 1 }])
  }

  const removeItem = (index: number) => {
    if (items.length > 1) {
      setItems(items.filter((_, i) => i !== index))
    }
  }

  const updateItem = (index: number, field: keyof OrderItemForm, value: string | number) => {
    const newItems: OrderItemForm[] = items.map((item, i) => i === index ? { ...item, [field]: value } : item)
    setItems(newItems)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!clientCodigo) {
      alert('Selecione um cliente')
      return
    }

    const validItems = items.filter((item) => item.product_codigo && item.quantity > 0)
    if (validItems.length === 0) {
      alert('Adicione pelo menos um item')
      return
    }

    try {
      const orderData = {
        client_codigo: clientCodigo,
        items: validItems.map((item) => ({
          product_codigo: String(item.product_codigo),
          quantity: item.quantity,
        })),
        delivery_fee: deliveryFee,
        discount: discount,
        payment_method: paymentMethod || undefined,
        source: 'MANUAL' as const,
        notes: notes || undefined,
      }

      const created = await createOrder.mutateAsync(orderData)
      navigate(`/orders/${created.codigo}`)
    } catch {
      // Error handled by mutation
    }
  }

  if (loadingCustomers || loadingProducts) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <Link
            to="/orders"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Link>
          <h1 className="text-2xl font-bold text-foreground">Novo Pedido</h1>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left Column - Form */}
          <div className="space-y-4 lg:col-span-2">
            {/* Customer Selection */}
            <Card>
              <CardHeader>
                <CardTitle>Cliente</CardTitle>
              </CardHeader>
              <CardContent>
                <select
                  value={clientCodigo}
                  onChange={(e) => setClientCodigo(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
                  required
                >
                  <option value="">Selecione um cliente</option>
                  {customers?.map((customer) => (
                    <option key={customer.codigo} value={customer.codigo}>
                      {customer.codigo} - {customer.nome} ({customer.bairro})
                    </option>
                  ))}
                </select>
                {selectedCustomer && (
                  <p className="mt-2 text-sm text-muted-foreground">
                    {selectedCustomer.rua}, {selectedCustomer.numero} - {selectedCustomer.bairro}
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Items */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>Itens</span>
                  <Button type="button" variant="outline" size="sm" onClick={addItem}>
                    <Plus className="h-4 w-4" />
                    Adicionar
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {items.map((item, index) => (
                  <div key={index} className="flex gap-3">
                    <select
                      value={item.product_codigo}
                      onChange={(e) => updateItem(index, 'product_codigo', e.target.value)}
                      className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
                      required
                    >
                      <option value="">Selecione um produto</option>
                      {products?.filter((p) => p.ativo).map((product) => (
                        <option key={product.codigo} value={product.codigo}>
                          {product.nome} - {formatCurrency(product.preco)} (Estoque: {product.estoque})
                        </option>
                      ))}
                    </select>
                    <Input
                      type="number"
                      min="1"
                      value={item.quantity}
                      onChange={(e) => updateItem(index, 'quantity', parseInt(e.target.value) || 1)}
                      className="w-24"
                      required
                    />
                    <p className="flex items-center text-sm font-medium text-foreground">
                      {formatCurrency(getProductPrice(item.product_codigo) * item.quantity)}
                    </p>
                    {items.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => removeItem(index)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* Payment & Notes */}
            <Card>
              <CardHeader>
                <CardTitle>Pagamento e Observações</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      Forma de Pagamento
                    </label>
                    <select
                      value={paymentMethod}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
                    >
                      <option value="">Selecione</option>
                      {paymentMethods.length > 0 ? (
                        paymentMethods.map(m => (
                          <option key={m.code} value={m.code}>{m.name}</option>
                        ))
                      ) : (
                        <>
                          <option value="Dinheiro">Dinheiro</option>
                          <option value="PIX">PIX</option>
                          <option value="CREDIT_CARD">Cartão de Crédito</option>
                          <option value="DEBIT_CARD">Cartão de Débito</option>
                          <option value="ON_ACCOUNT">Fiado</option>
                        </>
                      )}
                    </select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      Observações
                    </label>
                    <Input
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Observações do pedido"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right Column - Summary */}
          <div className="space-y-4">
            <Card className="sticky top-6">
              <CardHeader>
                <CardTitle>Resumo</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Subtotal</span>
                    <span className="text-sm text-foreground">{formatCurrency(subtotal)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Entrega</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={deliveryFee}
                      onChange={(e) => setDeliveryFee(parseFloat(e.target.value) || 0)}
                      className="w-24 text-right"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Desconto</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={discount}
                      onChange={(e) => setDiscount(parseFloat(e.target.value) || 0)}
                      className="w-24 text-right"
                    />
                  </div>
                  <div className="border-t border-border pt-2">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-foreground">Total</span>
                      <span className="text-xl font-bold text-foreground">
                        {formatCurrency(total)}
                      </span>
                    </div>
                  </div>
                </div>

                <Button
                  type="submit"
                  className="w-full"
                  disabled={createOrder.isPending}
                >
                  <ShoppingCart className="h-4 w-4" />
                  {createOrder.isPending ? 'Criando...' : 'Criar Pedido'}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </form>
    </div>
  )
}
