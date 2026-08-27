import { } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Phone, MapPin, Edit, Trash2, Clock, FileText, ShoppingCart, ShoppingBag, DollarSign, Calendar } from 'lucide-react'
import { useCustomer360, useCustomerOrders, useDisableCustomer } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { StatCard } from '@/components/ui/StatCard'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { ModulePlaceholder } from '@/components/layout/ModulePlaceholder'
import { formatPhone, formatDate, formatCurrency } from '@/lib/utils'

const CLIENT_TYPES: Record<string, string> = {
  CONSUMER: 'Consumidor',
  RESTAURANT: 'Restaurante',
  COMPANY: 'Empresa',
  SCHOOL: 'Escola',
  OTHER: 'Outro',
}

export function CustomerDetailPage() {
  const { codigo } = useParams<{ codigo: string }>()
  const navigate = useNavigate()
  const { data: customer, isLoading, error, refetch } = useCustomer360(codigo ?? '')
  const { data: orders = [] } = useCustomerOrders(codigo ?? '')
  const disableCustomer = useDisableCustomer()

  const handleDisable = async () => {
    if (!customer) return
    if (window.confirm(`Deseja desativar o cliente ${customer.nome}?`)) {
      await disableCustomer.mutateAsync(customer.codigo)
      navigate('/customers')
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error || !customer) {
    return (
      <ErrorState
        message="Não foi possível carregar os dados do cliente."
        onRetry={() => refetch()}
      />
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <Link
            to="/customers"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-foreground">{customer.nome}</h1>
            <Badge variant={customer.ativo ? 'success' : 'secondary'}>
              {customer.ativo ? 'Ativo' : 'Inativo'}
            </Badge>
            {customer.tipo && (
              <Badge variant="outline">
                {CLIENT_TYPES[customer.tipo] ?? customer.tipo}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
              <Phone className="h-4 w-4" />
              {formatPhone(customer.telefone)}
            </span>
            <span>Código: {customer.codigo}</span>
            {customer.email && <span>{customer.email}</span>}
          </div>
        </div>
        <div className="flex gap-2">
          <Link to={`/customers/${customer.codigo}/edit`}>
            <Button variant="outline">
              <Edit className="h-4 w-4" />
              Editar
            </Button>
          </Link>
          <Button variant="destructive" onClick={handleDisable}>
            <Trash2 className="h-4 w-4" />
            Desativar
          </Button>
        </div>
      </div>      {/* CRM Metrics */}
      {customer.total_orders > 0 && (
        <div className="grid gap-4 md:grid-cols-4">
          <StatCard title="Total de Pedidos" value={String(customer.total_orders)} icon={ShoppingCart} />
          <StatCard title="Total Gasto" value={formatCurrency(customer.total_spent)} icon={DollarSign} />
          <StatCard title="Ticket Médio" value={formatCurrency(customer.average_ticket)} icon={ShoppingBag} />
          <StatCard
            title="Última Compra"
            value={customer.days_since_last_order !== null ? `${customer.days_since_last_order}d atrás` : '—'}
            icon={Calendar}
          />
        </div>
      )}

      {/* FASE 6+8: Favorite Product + Financial Metrics */}
      {customer.total_orders > 0 && (
        <div className="grid gap-4 md:grid-cols-3">
          {customer.favorite_product && (
            <StatCard title="Produto Favorito" value={customer.favorite_product} icon={ShoppingBag} />
          )}
          {(customer.outstanding_balance ?? 0) > 0 && (
            <StatCard title="Saldo Pendente" value={formatCurrency(customer.outstanding_balance ?? 0)} icon={DollarSign} />
          )}
          {(customer.paid_amount ?? 0) > 0 && (
            <StatCard title="Total Pago" value={formatCurrency(customer.paid_amount ?? 0)} icon={DollarSign} />
          )}
        </div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="summary">
        <TabsList>
          <TabsTrigger value="summary">Resumo</TabsTrigger>
          <TabsTrigger value="orders">Pedidos</TabsTrigger>
          <TabsTrigger value="addresses">Endereços</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="notes">Notas</TabsTrigger>
        </TabsList>

        <TabsContent value="summary" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Informações do Cliente</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <p className="text-sm text-muted-foreground">Nome</p>
                  <p className="font-medium text-foreground">{customer.nome}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Código</p>
                  <p className="font-medium text-foreground">{customer.codigo}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Telefone</p>
                  <p className="font-medium text-foreground">
                    {formatPhone(customer.telefone)}
                  </p>
                </div>
                {customer.telefone_secundario && (
                  <div>
                    <p className="text-sm text-muted-foreground">Telefone Secundário</p>
                    <p className="font-medium text-foreground">
                      {formatPhone(customer.telefone_secundario)}
                    </p>
                  </div>
                )}
                {customer.tipo && (
                  <div>
                    <p className="text-sm text-muted-foreground">Tipo</p>
                    <p className="font-medium text-foreground">
                      {CLIENT_TYPES[customer.tipo] ?? customer.tipo}
                    </p>
                  </div>
                )}
                {customer.email && (
                  <div>
                    <p className="text-sm text-muted-foreground">Email</p>
                    <p className="font-medium text-foreground">{customer.email}</p>
                  </div>
                )}
                <div>
                  <p className="text-sm text-muted-foreground">Criado em</p>
                  <p className="font-medium text-foreground">
                    {formatDate(customer.created_at)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Atualizado em</p>
                  <p className="font-medium text-foreground">
                    {formatDate(customer.updated_at)}
                  </p>
                </div>
              </div>

              {customer.observacoes && (
                <div>
                  <p className="text-sm text-muted-foreground">Observações</p>
                  <p className="text-foreground">{customer.observacoes}</p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Endereço</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-start gap-3">
                <MapPin className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="font-medium text-foreground">
                    {customer.rua}, {customer.numero}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {customer.bairro}
                    {customer.complemento && ` - ${customer.complemento}`}
                  </p>
                  {customer.referencia && (
                    <p className="text-xs text-muted-foreground">
                      Referência: {customer.referencia}
                    </p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="orders" className="space-y-4">
          {orders.length === 0 ? (
            <Card>
              <CardContent className="py-8">
                <div className="flex flex-col items-center text-center">
                  <ShoppingCart className="h-12 w-12 text-muted-foreground" />
                  <h3 className="mt-4 text-lg font-semibold text-foreground">
                    Nenhum pedido encontrado
                  </h3>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Este cliente ainda não realizou nenhum pedido.
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Pedidos Recentes ({orders.length})</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {orders.map((order) => (
                    <Link
                      key={order.codigo}
                      to={`/orders/${order.codigo}`}
                      className="flex items-center justify-between rounded-lg border border-border p-4 transition-colors hover:bg-accent/50"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-foreground">Pedido #{order.codigo}</p>
                          <Badge variant={
                            order.status === 'DELIVERED' ? 'success' :
                            order.status === 'CANCELLED' ? 'destructive' :
                            'default'
                          }>
                            {order.status}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {formatDate(order.created_at)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-medium text-foreground">
                          {formatCurrency(order.total)}
                        </p>
                      </div>
                    </Link>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="addresses">
          <Card>
            <CardContent className="py-8">
              <div className="flex flex-col items-center text-center">
                <MapPin className="h-12 h-12 text-muted-foreground" />
                <h3 className="mt-4 text-lg font-semibold text-foreground">
                  Endereço Principal
                </h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  {customer.rua}, {customer.numero} - {customer.bairro}
                </p>
                {customer.complemento && (
                  <p className="text-xs text-muted-foreground">{customer.complemento}</p>
                )}
                {customer.referencia && (
                  <p className="text-xs text-muted-foreground">
                    Referência: {customer.referencia}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="timeline">
          <ModulePlaceholder
            icon={Clock}
            title="Timeline"
            description="Histórico de interações e pedidos do cliente"
          />
        </TabsContent>

        <TabsContent value="notes">
          <ModulePlaceholder
            icon={FileText}
            title="Notas"
            description="Anotações e observações sobre o cliente"
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
