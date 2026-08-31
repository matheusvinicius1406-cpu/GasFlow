import { Link } from 'react-router-dom'
import {
  ShoppingCart,
  Users,
  Package,
  Truck,
  DollarSign,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  ArrowRight,
  Clock,
  CheckCircle,
  Wallet,
  BarChart3,
  Zap,
} from 'lucide-react'
import { useAuth } from '@/features/auth'
import { useDashboard } from '@/lib/api/hooks'
import { cn, formatCurrency, formatDate } from '@/lib/utils'
import { getStatusConfig, ORDER_STATUS } from '@/lib/status'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'

// ── Greeting ───────────────────────────────────────────────

function getGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Bom dia'
  if (hour < 18) return 'Boa tarde'
  return 'Boa noite'
}

function getFormattedDate(): string {
  return new Intl.DateTimeFormat('pt-BR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(new Date())
}

// ── KPI Card ───────────────────────────────────────────────

interface KpiCardProps {
  title: string
  value: string | number
  icon: React.ElementType
  trend?: { value: number; positive: boolean }
  subtitle?: string
  color?: string
  className?: string
}

function KpiCard({ title, value, icon: Icon, trend, subtitle, color = 'text-primary', className }: KpiCardProps) {
  return (
    <Card className={cn('relative overflow-hidden', className)}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground">{value}</p>
            {subtitle && (
              <p className="text-xs text-muted-foreground">{subtitle}</p>
            )}
          </div>
          <div className={cn('rounded-lg bg-primary/10 p-2.5', color === 'text-primary' ? '' : '')}>
            <Icon className={cn('h-5 w-5', color)} />
          </div>
        </div>
        {trend && (
          <div className="mt-3 flex items-center gap-1">
            {trend.positive ? (
              <TrendingUp className="h-3.5 w-3.5 text-success" />
            ) : (
              <TrendingDown className="h-3.5 w-3.5 text-destructive" />
            )}
            <span className={cn(
              'text-xs font-medium',
              trend.positive ? 'text-success' : 'text-destructive'
            )}>
              {trend.positive ? '+' : ''}{trend.value}%
            </span>
            <span className="text-xs text-muted-foreground">vs. ontem</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Alert Item ─────────────────────────────────────────────

interface AlertItemProps {
  type: 'warning' | 'danger' | 'info'
  title: string
  description: string
  action: string
}

const ALERT_CONFIG = {
  warning: { icon: AlertTriangle, color: 'text-warning', bg: 'bg-warning/10' },
  danger: { icon: AlertTriangle, color: 'text-destructive', bg: 'bg-destructive/10' },
  info: { icon: Zap, color: 'text-info', bg: 'bg-info/10' },
}

function AlertItem({ type, title, description, action }: AlertItemProps) {
  const config = ALERT_CONFIG[type]
  const Icon = config.icon

  return (
    <Link
      to={action}
      className={cn(
        'flex items-start gap-3 rounded-lg border border-border p-3',
        'transition-colors hover:bg-accent/50'
      )}
    >
      <div className={cn('rounded-md p-1.5', config.bg)}>
        <Icon className={cn('h-4 w-4', config.color)} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
      <ArrowRight className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
    </Link>
  )
}

// ── Stock Bar ──────────────────────────────────────────────

function StockBar({ label, current, minimum }: { label: string; current: number; minimum: number }) {
  const max = Math.max(current, minimum * 2, 100)
  const percentage = (current / max) * 100
  const isLow = minimum > 0 && current <= minimum
  const isEmpty = current === 0

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-foreground">{label}</span>
        <span className={cn(
          'text-sm font-bold',
          isEmpty ? 'text-destructive' : isLow ? 'text-warning' : 'text-foreground'
        )}>
          {current}
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500',
            isEmpty ? 'bg-destructive' : isLow ? 'bg-warning' : 'bg-primary'
          )}
          style={{ width: `${Math.max(percentage, 2)}%` }}
        />
      </div>
    </div>
  )
}

// ── Main Dashboard ─────────────────────────────────────────

export function DashboardPage() {
  const { user } = useAuth()
  const { data: dashboard, isLoading, error } = useDashboard()

  if (isLoading) {
    return (
      <Page>
        <PageHeader>
          <div className="space-y-1">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-48" />
          </div>
        </PageHeader>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-8 w-20 mb-1" />
                <Skeleton className="h-3 w-32" />
              </CardContent>
            </Card>
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <Card><CardContent className="p-5"><Skeleton className="h-64 w-full" /></CardContent></Card>
          <Card><CardContent className="p-5"><Skeleton className="h-64 w-full" /></CardContent></Card>
        </div>
      </Page>
    )
  }

  if (error) {
    return (
      <Page>
        <PageHeader>
          <PageTitle subtitle="Erro ao carregar dados">Dashboard</PageTitle>
        </PageHeader>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
            <h3 className="text-lg font-semibold">Não foi possível carregar o dashboard</h3>
            <p className="text-sm text-muted-foreground mt-2">Tente novamente em alguns instantes.</p>
          </CardContent>
        </Card>
      </Page>
    )
  }

  const s = dashboard?.summary
  const f = dashboard?.financial
  const inv = dashboard?.inventory
  const alerts = dashboard?.alerts ?? []
  const recentOrders = dashboard?.recent_orders ?? []

  const greetingName = user?.name?.split(' ')[0] ?? 'Operador'

  return (
    <Page>
      {/* Header */}
      <PageHeader>
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            {getGreeting()}, {greetingName}
          </h1>
          <p className="text-sm text-muted-foreground">
            Visão geral da operação • {getFormattedDate()}
          </p>
        </div>
        <PageActions>
          <Link to="/orders/new">
            <Button>
              <ShoppingCart className="h-4 w-4" />
              Novo Pedido
            </Button>
          </Link>
        </PageActions>
      </PageHeader>

      {/* KPI Row */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Pedidos Hoje"
          value={s?.today_orders ?? 0}
          icon={ShoppingCart}
          subtitle={`${s?.total_orders ?? 0} total`}
          color="text-primary"
        />
        <KpiCard
          title="Faturamento Hoje"
          value={formatCurrency(s?.today_revenue ?? 0)}
          icon={DollarSign}
          subtitle={`${formatCurrency(s?.total_revenue ?? 0)} total`}
          color="text-success"
        />
        <KpiCard
          title="Em Rota"
          value={s?.delivering_orders ?? 0}
          icon={Truck}
          subtitle={`${s?.delivered_orders ?? 0} entregues`}
          color="text-info"
        />
        <KpiCard
          title="Ticket Médio"
          value={formatCurrency(s?.avg_ticket ?? 0)}
          icon={BarChart3}
          subtitle={`${s?.total_orders ?? 0} pedidos`}
          color="text-secondary-foreground"
        />
      </div>

      {/* Financial Quick View */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Saldo em Caixa"
          value={formatCurrency(f?.cash_balance ?? 0)}
          icon={Wallet}
          color="text-success"
        />
        <KpiCard
          title="Recebido Hoje"
          value={formatCurrency(f?.today_received ?? 0)}
          icon={TrendingUp}
          subtitle={`${formatCurrency(f?.total_received ?? 0)} total`}
          color="text-success"
        />
        <KpiCard
          title="A Receber"
          value={formatCurrency(f?.total_pending ?? 0)}
          icon={Clock}
          color="text-warning"
        />
        <KpiCard
          title="Resultado"
          value={formatCurrency(f?.result ?? 0)}
          icon={(f?.result ?? 0) >= 0 ? TrendingUp : TrendingDown}
          color={(f?.result ?? 0) >= 0 ? 'text-success' : 'text-destructive'}
        />
      </div>

      {/* Main Content */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Recent Orders — 2 cols */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-semibold text-foreground">Pedidos Recentes</h2>
                <Link to="/orders">
                  <Button variant="ghost" size="sm">
                    Ver todos <ArrowRight className="h-3.5 w-3.5 ml-1" />
                  </Button>
                </Link>
              </div>

              {recentOrders.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <ShoppingCart className="h-10 w-10 text-muted-foreground/50 mb-3" />
                  <p className="text-sm text-muted-foreground">Nenhum pedido ainda</p>
                  <Link to="/orders/new" className="mt-3">
                    <Button size="sm">
                      <ShoppingCart className="h-3.5 w-3.5" />
                      Criar primeiro pedido
                    </Button>
                  </Link>
                </div>
              ) : (
                <div className="space-y-2">
                  {recentOrders.map((order) => {
                    const statusConfig = getStatusConfig(order.status, ORDER_STATUS)
                    return (
                      <Link
                        key={order.codigo}
                        to={`/orders/${order.codigo}`}
                        className={cn(
                          'flex items-center justify-between rounded-lg border border-border p-3',
                          'transition-colors hover:bg-accent/50'
                        )}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="rounded-full bg-muted p-2 flex-shrink-0">
                            <ShoppingCart className="h-4 w-4 text-muted-foreground" />
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-medium text-foreground">#{order.codigo}</p>
                              <Badge variant={statusConfig.variant} className="text-xs">
                                {statusConfig.label}
                              </Badge>
                            </div>
                            <p className="text-xs text-muted-foreground truncate">
                              {order.client_codigo}
                              {order.created_at && ` • ${formatDate(order.created_at)}`}
                            </p>
                          </div>
                        </div>
                        <div className="text-right flex-shrink-0 ml-3">
                          <p className="text-sm font-bold text-foreground">
                            {formatCurrency(order.total)}
                          </p>
                          <Badge
                            variant={order.payment_status === 'PAID' ? 'success' : 'secondary'}
                            className="text-xs mt-0.5"
                          >
                            {order.payment_status === 'PAID' ? 'Pago' : 'Pendente'}
                          </Badge>
                        </div>
                      </Link>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Stock Overview */}
          {(inv?.low_stock_count ?? 0) > 0 || (inv?.out_of_stock_count ?? 0) > 0 ? (
            <Card>
              <CardContent className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-base font-semibold text-foreground">Estoque</h2>
                  <Link to="/inventory">
                    <Button variant="ghost" size="sm">
                      Ver estoque <ArrowRight className="h-3.5 w-3.5 ml-1" />
                    </Button>
                  </Link>
                </div>

                <div className="flex items-center gap-4 mb-4">
                  {(inv?.out_of_stock_count ?? 0) > 0 && (
                    <div className="flex items-center gap-1.5">
                      <div className="h-2 w-2 rounded-full bg-destructive" />
                      <span className="text-xs text-muted-foreground">
                        {inv?.out_of_stock_count} sem estoque
                      </span>
                    </div>
                  )}
                  {(inv?.low_stock_count ?? 0) > 0 && (
                    <div className="flex items-center gap-1.5">
                      <div className="h-2 w-2 rounded-full bg-warning" />
                      <span className="text-xs text-muted-foreground">
                        {inv?.low_stock_count} estoque baixo
                      </span>
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  {(inv?.low_stock_products ?? []).map((item) => (
                    <StockBar
                      key={item.product_codigo}
                      label={item.product_codigo}
                      current={item.quantity}
                      minimum={item.minimum}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>

        {/* Alerts Sidebar */}
        <div className="space-y-4">
          <Card>
            <CardContent className="p-5">
              <h2 className="text-base font-semibold text-foreground mb-4">Alertas & Ações</h2>
              {alerts.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-6 text-center">
                  <CheckCircle className="h-8 w-8 text-success mb-2" />
                  <p className="text-sm text-muted-foreground">Tudo em ordem!</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {alerts.map((alert, i) => (
                    <AlertItem key={i} {...alert} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Quick Stats */}
          <Card>
            <CardContent className="p-5">
              <h2 className="text-base font-semibold text-foreground mb-4">Resumo</h2>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Users className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">Clientes</span>
                  </div>
                  <span className="text-sm font-bold text-foreground">{dashboard?.clients?.total ?? 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Package className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">Produtos</span>
                  </div>
                  <span className="text-sm font-bold text-foreground">{dashboard?.products?.total ?? 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Truck className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">Motoristas</span>
                  </div>
                  <span className="text-sm font-bold text-foreground">{dashboard?.drivers?.total ?? 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Package className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">Itens em Estoque</span>
                  </div>
                  <span className="text-sm font-bold text-foreground">{inv?.total_items ?? 0}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Page>
  )
}
