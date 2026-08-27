import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Warehouse, Search, Package, AlertTriangle, XCircle, ChevronRight } from 'lucide-react'
import { useInventoryList, useProducts } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatCurrency } from '@/lib/utils'
import type { Product, StockStatus } from '@/types'

const STOCK_STATUS_CONFIG: Record<StockStatus, { label: string; variant: string; icon: typeof Package }> = {
  IN_STOCK: { label: 'Em Estoque', variant: 'success', icon: Package },
  LOW_STOCK: { label: 'Estoque Baixo', variant: 'warning', icon: AlertTriangle },
  OUT_OF_STOCK: { label: 'Sem Estoque', variant: 'destructive', icon: XCircle },
}

const PRODUCT_TYPES = [
  { value: '', label: 'Todos os tipos' },
  { value: 'GAS', label: 'Gás' },
  { value: 'AGUA', label: 'Água' },
]

export function InventoryPage() {
  const [search, setSearch] = useState('')
  const [tipoFilter, setTipoFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | string>('all')

  const { data: inventoryData, isLoading: isLoadingInventory, error: inventoryError, refetch } = useInventoryList({
    stock_status: statusFilter !== 'all' ? statusFilter : undefined,
    product_type: tipoFilter || undefined,
  })

  const { data: products = [] } = useProducts()

  const inventoryItems = inventoryData?.items ?? []
  const total = inventoryData?.total ?? 0

  const enrichedItems = inventoryItems.map(item => {
    const product = (products as Product[]).find(p => p.codigo === item.product_codigo)
    return { ...item, product }
  }).filter(item => {
    if (!search) return true
    const q = search.toLowerCase()
    const name = item.product?.nome?.toLowerCase() ?? ''
    const code = item.product_codigo.toLowerCase()
    return name.includes(q) || code.includes(q)
  })

  if (isLoadingInventory) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (inventoryError) {
    return (
      <ErrorState
        message="Não foi possível carregar o inventário."
        onRetry={() => refetch()}
      />
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Estoque</h1>
          <p className="text-muted-foreground">
            {total} produtos no inventário
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Buscar por nome ou código..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <div className="flex gap-2">
          <select
            value={tipoFilter}
            onChange={(e) => setTipoFilter(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm"
          >
            {PRODUCT_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <Button
            variant={statusFilter === 'all' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter('all')}
          >
            Todos
          </Button>
          <Button
            variant={statusFilter === 'IN_STOCK' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter('IN_STOCK')}
          >
            Em Estoque
          </Button>
          <Button
            variant={statusFilter === 'LOW_STOCK' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter('LOW_STOCK')}
          >
            Baixo
          </Button>
          <Button
            variant={statusFilter === 'OUT_OF_STOCK' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter('OUT_OF_STOCK')}
          >
            Zerado
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-green-100 p-2 dark:bg-green-900/30">
                <Package className="h-5 w-5 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Em Estoque</p>
                <p className="text-lg font-bold text-foreground">
                  {inventoryItems.filter(i => i.stock_status === 'IN_STOCK').length}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-yellow-100 p-2 dark:bg-yellow-900/30">
                <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Estoque Baixo</p>
                <p className="text-lg font-bold text-foreground">
                  {inventoryItems.filter(i => i.stock_status === 'LOW_STOCK').length}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-red-100 p-2 dark:bg-red-900/30">
                <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Sem Estoque</p>
                <p className="text-lg font-bold text-foreground">
                  {inventoryItems.filter(i => i.stock_status === 'OUT_OF_STOCK').length}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Inventory List */}
      {enrichedItems.length === 0 ? (
        <EmptyState
          icon={Warehouse}
          title={search ? 'Nenhum produto encontrado' : 'Nenhum produto no inventário'}
          description={
            search
              ? 'Nenhum produto corresponde aos filtros aplicados.'
              : 'O inventário será populado quando produtos forem cadastrados.'
          }
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Produtos</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {enrichedItems.map((item) => {
                const statusConfig = STOCK_STATUS_CONFIG[item.stock_status as StockStatus] ?? STOCK_STATUS_CONFIG.IN_STOCK
                const StatusIcon = statusConfig.icon
                return (
                  <Link
                    key={item.product_codigo}
                    to={`/inventory/${item.product_codigo}`}
                    className="flex items-center justify-between rounded-lg border border-border p-4 transition-colors hover:bg-accent/50"
                  >
                    <div className="flex items-center gap-4">
                      <div className="rounded-full bg-muted p-2">
                        <StatusIcon className="h-5 w-5" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-foreground">
                            {item.product?.nome ?? item.product_codigo}
                          </p>
                          <Badge variant={statusConfig.variant as 'success' | 'warning' | 'destructive'}>
                            {statusConfig.label}
                          </Badge>
                          {item.product?.tipo && (
                            <Badge variant="outline">
                              {item.product.tipo === 'GAS' ? 'Gás' : 'Água'}
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Código: {item.product_codigo}
                          {item.product?.preco !== undefined && (
                            <> • {formatCurrency(item.product.preco)}</>
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="text-lg font-bold text-foreground">{item.quantity}</p>
                        <p className="text-xs text-muted-foreground">
                          {item.minimum_quantity > 0 && `Mín: ${item.minimum_quantity}`}
                        </p>
                      </div>
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </Link>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
