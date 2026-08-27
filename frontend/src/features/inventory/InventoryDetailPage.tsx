import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Package, Minus, Plus, Edit, History, AlertTriangle } from 'lucide-react'
import { useInventoryItem, useInventoryMovements, useProducts, useAddStock, useAdjustStock, useRecordLoss } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { StatCard } from '@/components/ui/StatCard'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { formatCurrency, formatDateTime } from '@/lib/utils'
import type { Product, StockStatus } from '@/types'

const STOCK_STATUS_CONFIG: Record<StockStatus, { label: string; variant: string }> = {
  IN_STOCK: { label: 'Em Estoque', variant: 'success' },
  LOW_STOCK: { label: 'Estoque Baixo', variant: 'warning' },
  OUT_OF_STOCK: { label: 'Sem Estoque', variant: 'destructive' },
}

const MOVEMENT_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  ENTRY: { label: 'Entrada', color: 'text-green-600' },
  SALE: { label: 'Venda', color: 'text-red-600' },
  ADJUSTMENT: { label: 'Ajuste', color: 'text-blue-600' },
  LOSS: { label: 'Perda', color: 'text-orange-600' },
  RETURN: { label: 'Devolução', color: 'text-purple-600' },
  INITIAL_BALANCE: { label: 'Saldo Inicial', color: 'text-gray-600' },
}

export function InventoryDetailPage() {
  const { productCodigo } = useParams<{ productCodigo: string }>()
  const [entryQty, setEntryQty] = useState('')
  const [entryReason, setEntryReason] = useState('')
  const [adjustQty, setAdjustQty] = useState('')
  const [adjustReason, setAdjustReason] = useState('')
  const [lossQty, setLossQty] = useState('')
  const [lossReason, setLossReason] = useState('')
  const [movementsPage, setMovementsPage] = useState(1)

  const { data: inventory, isLoading, error, refetch } = useInventoryItem(productCodigo ?? '')
  const { data: movementsData, isLoading: isLoadingMovements } = useInventoryMovements(productCodigo ?? '', movementsPage)
  const { data: products = [] } = useProducts()
  const addStock = useAddStock()
  const adjustStock = useAdjustStock()
  const recordLoss = useRecordLoss()

  const product = (products as Product[]).find(p => p.codigo === productCodigo)

  const handleAddStock = async () => {
    if (!entryQty || parseInt(entryQty) <= 0) return
    await addStock.mutateAsync({
      codigo: productCodigo!,
      quantity: parseInt(entryQty),
      reason: entryReason || 'Entrada de estoque',
    })
    setEntryQty('')
    setEntryReason('')
  }

  const handleAdjust = async () => {
    if (adjustQty === '' || parseInt(adjustQty) < 0) return
    await adjustStock.mutateAsync({
      codigo: productCodigo!,
      new_quantity: parseInt(adjustQty),
      reason: adjustReason || 'Ajuste de inventário',
    })
    setAdjustQty('')
    setAdjustReason('')
  }

  const handleLoss = async () => {
    if (!lossQty || parseInt(lossQty) <= 0 || !lossReason) return
    await recordLoss.mutateAsync({
      codigo: productCodigo!,
      quantity: parseInt(lossQty),
      reason: lossReason,
    })
    setLossQty('')
    setLossReason('')
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error || !inventory) {
    return (
      <ErrorState
        message="Não foi possível carregar os dados de inventário."
        onRetry={() => refetch()}
      />
    )
  }

  const statusConfig = STOCK_STATUS_CONFIG[inventory.stock_status as StockStatus] ?? STOCK_STATUS_CONFIG.IN_STOCK
  const movements = movementsData?.items ?? []
  const totalMovements = movementsData?.total ?? 0
  const totalMovementPages = movementsData?.total_pages ?? 1

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <Link
            to="/inventory"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-foreground">
              {product?.nome ?? inventory.product_codigo}
            </h1>
            <Badge variant={statusConfig.variant as 'success' | 'warning' | 'destructive'}>
              {statusConfig.label}
            </Badge>
            {product?.tipo && (
              <Badge variant="outline">
                {product.tipo === 'GAS' ? 'Gás' : 'Água'}
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            Código: {inventory.product_codigo}
            {product?.preco !== undefined && <> • Preço: {formatCurrency(product.preco)}</>}
          </p>
        </div>
      </div>

      {/* Stock Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <StatCard title="Estoque Atual" value={String(inventory.quantity)} icon={Package} />
        <StatCard title="Mínimo" value={String(inventory.minimum_quantity)} icon={Minus} />
        <StatCard
          title="Status"
          value={statusConfig.label}
          icon={inventory.stock_status === 'OUT_OF_STOCK' ? Minus : Package}
        />
        <StatCard title="Total Movimentações" value={String(totalMovements)} icon={History} />
      </div>

      <Tabs defaultValue="movements">
        <TabsList>
          <TabsTrigger value="movements">Movimentações</TabsTrigger>
          <TabsTrigger value="entry">Entrada</TabsTrigger>
          <TabsTrigger value="adjust">Ajuste</TabsTrigger>
          <TabsTrigger value="loss">Perda</TabsTrigger>
        </TabsList>

        <TabsContent value="movements" className="space-y-4">
          {isLoadingMovements ? (
            <div className="flex justify-center py-8">
              <LoadingSpinner />
            </div>
          ) : movements.length === 0 ? (
            <EmptyState
              icon={History}
              title="Nenhuma movimentação"
              description="Ainda não houve movimentações de estoque para este produto."
            />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Histórico de Movimentações ({totalMovements})</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="pb-2 text-left text-muted-foreground">Data</th>
                        <th className="pb-2 text-left text-muted-foreground">Tipo</th>
                        <th className="pb-2 text-right text-muted-foreground">Quantidade</th>
                        <th className="pb-2 text-right text-muted-foreground">Antes</th>
                        <th className="pb-2 text-right text-muted-foreground">Depois</th>
                        <th className="pb-2 text-left text-muted-foreground">Motivo</th>
                        <th className="pb-2 text-left text-muted-foreground">Referência</th>
                      </tr>
                    </thead>
                    <tbody>
                      {movements.map((m) => {
                        const typeConfig = MOVEMENT_TYPE_CONFIG[m.type] ?? { label: m.type, color: 'text-foreground' }
                        const isEntry = ['ENTRY', 'RETURN', 'INITIAL_BALANCE'].includes(m.type)
                        return (
                          <tr key={m.id} className="border-b border-border/50">
                            <td className="py-3 text-foreground">
                              {m.created_at ? formatDateTime(m.created_at) : '—'}
                            </td>
                            <td className="py-3">
                              <Badge variant={isEntry ? 'success' : m.type === 'SALE' ? 'destructive' : 'outline'}>
                                {typeConfig.label}
                              </Badge>
                            </td>
                            <td className={`py-3 text-right font-medium ${typeConfig.color}`}>
                              {isEntry ? '+' : '-'}{m.quantity}
                            </td>
                            <td className="py-3 text-right text-muted-foreground">{m.balance_before}</td>
                            <td className="py-3 text-right font-medium text-foreground">{m.balance_after}</td>
                            <td className="py-3 text-muted-foreground">{m.reason}</td>
                            <td className="py-3 text-muted-foreground">
                              {m.reference_type && m.reference_id
                                ? `${m.reference_type} #${m.reference_id}`
                                : '—'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {totalMovementPages > 1 && (
                  <div className="mt-4 flex items-center justify-between">
                    <p className="text-sm text-muted-foreground">
                      Página {movementsPage} de {totalMovementPages}
                    </p>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setMovementsPage(p => Math.max(1, p - 1))}
                        disabled={movementsPage <= 1}
                      >
                        Anterior
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setMovementsPage(p => Math.min(totalMovementPages, p + 1))}
                        disabled={movementsPage >= totalMovementPages}
                      >
                        Próxima
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="entry" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Entrada de Estoque</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Quantidade</label>
                  <Input
                    type="number"
                    min="1"
                    value={entryQty}
                    onChange={(e) => setEntryQty(e.target.value)}
                    placeholder="Quantidade a entrar"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Motivo</label>
                  <Input
                    value={entryReason}
                    onChange={(e) => setEntryReason(e.target.value)}
                    placeholder="Ex: Compra de fornecedor"
                  />
                </div>
              </div>
              <Button
                onClick={handleAddStock}
                disabled={!entryQty || parseInt(entryQty) <= 0 || addStock.isPending}
              >
                <Plus className="h-4 w-4" />
                {addStock.isPending ? 'Registrando...' : 'Registrar Entrada'}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="adjust" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Ajuste de Estoque</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Estoque atual: <span className="font-medium text-foreground">{inventory.quantity}</span>
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Nova Quantidade (contagem física)</label>
                  <Input
                    type="number"
                    min="0"
                    value={adjustQty}
                    onChange={(e) => setAdjustQty(e.target.value)}
                    placeholder="Quantidade contada"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Motivo</label>
                  <Input
                    value={adjustReason}
                    onChange={(e) => setAdjustReason(e.target.value)}
                    placeholder="Ex: Contagem física"
                  />
                </div>
              </div>
              <Button
                variant="outline"
                onClick={handleAdjust}
                disabled={adjustQty === '' || parseInt(adjustQty) < 0 || adjustStock.isPending}
              >
                <Edit className="h-4 w-4" />
                {adjustStock.isPending ? 'Ajustando...' : 'Ajustar Estoque'}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="loss" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Registrar Perda</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Estoque atual: <span className="font-medium text-foreground">{inventory.quantity}</span>
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Quantidade Perdida</label>
                  <Input
                    type="number"
                    min="1"
                    value={lossQty}
                    onChange={(e) => setLossQty(e.target.value)}
                    placeholder="Quantidade perdida"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Motivo *</label>
                  <Input
                    value={lossReason}
                    onChange={(e) => setLossReason(e.target.value)}
                    placeholder="Ex: Vazamento, quebra"
                  />
                </div>
              </div>
              <Button
                variant="destructive"
                onClick={handleLoss}
                disabled={!lossQty || parseInt(lossQty) <= 0 || !lossReason || recordLoss.isPending}
              >
                <AlertTriangle className="h-4 w-4" />
                {recordLoss.isPending ? 'Registrando...' : 'Registrar Perda'}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
