import { useParams, Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Edit, Trash2, Boxes } from 'lucide-react'
import { useProduct, useDisableProduct, useInventoryItem } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { formatCurrency, formatDate } from '@/lib/utils'

export function ProductDetailPage() {
  const { codigo } = useParams<{ codigo: string }>()
  const navigate = useNavigate()
  const { data: product, isLoading, error, refetch } = useProduct(codigo ?? '')
  const { data: inventory } = useInventoryItem(codigo ?? '')
  const disableProduct = useDisableProduct()

  const handleDisable = async () => {
    if (!product) return
    if (window.confirm(`Deseja desativar o produto ${product.nome}?`)) {
      await disableProduct.mutateAsync(product.codigo)
      navigate('/products')
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error || !product) {
    return (
      <ErrorState
        message="Não foi possível carregar os dados do produto."
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
            to="/products"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-foreground">{product.nome}</h1>
            <Badge variant={product.tipo === 'GAS' ? 'info' : 'secondary'}>
              {product.tipo === 'GAS' ? 'Gás' : 'Água'}
            </Badge>
            <Badge variant={product.ativo ? 'success' : 'secondary'}>
              {product.ativo ? 'Ativo' : 'Inativo'}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">Código: {product.codigo}</p>
        </div>
        <div className="flex gap-2">
          <Link to={`/products/${product.codigo}/edit`}>
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
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Product Info */}
        <Card>
          <CardHeader>
            <CardTitle>Informações do Produto</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Nome</p>
                <p className="font-medium text-foreground">{product.nome}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Código</p>
                <p className="font-medium text-foreground">{product.codigo}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Tipo</p>
                <p className="font-medium text-foreground">
                  {product.tipo === 'GAS' ? 'Gás (GLP)' : 'Água'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Preço</p>
                <p className="text-2xl font-bold text-foreground">
                  {formatCurrency(product.preco)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Stock Info — FASE 7: uses Inventory as source of truth */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Estoque</CardTitle>
              <Link to={`/inventory/${codigo}`}>
                <Button variant="ghost" size="sm">Ver Inventário →</Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="rounded-lg bg-primary/10 p-4">
                <Boxes className="h-8 w-8 text-primary" />
              </div>
              <div>
                <p className="text-3xl font-bold text-foreground">
                  {inventory ? inventory.quantity : product.estoque}
                </p>
                <p className="text-sm text-muted-foreground">unidades em estoque</p>
              </div>
            </div>

            {inventory && inventory.minimum_quantity > 0 && inventory.quantity <= inventory.minimum_quantity && (
              <div className="rounded-md bg-warning/10 p-3">
                <p className="text-sm text-warning">
                  Estoque baixo! Mínimo: {inventory.minimum_quantity}. Considere repor o estoque.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Timestamps */}
      <Card>
        <CardContent className="py-4">
          <div className="flex gap-6 text-sm text-muted-foreground">
            <span>Criado em: {formatDate(product.created_at)}</span>
            <span>Atualizado em: {formatDate(product.updated_at)}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
