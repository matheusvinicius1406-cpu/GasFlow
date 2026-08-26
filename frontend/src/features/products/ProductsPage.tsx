import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Package, Plus, Search } from 'lucide-react'
import { useProducts } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatCurrency } from '@/lib/utils'

export function ProductsPage() {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'GAS' | 'AGUA'>('all')

  const { data: products, isLoading, error, refetch } = useProducts()
  

  const filteredProducts = (products ?? []).filter((p) => {
    const matchesSearch =
      p.nome.toLowerCase().includes(search.toLowerCase()) ||
      p.codigo.includes(search)

    const matchesFilter = filter === 'all' || p.tipo === filter

    return matchesSearch && matchesFilter
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
        message="Não foi possível carregar os produtos."
        onRetry={() => refetch()}
      />
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Produtos</h1>
          <p className="text-muted-foreground">
            {products?.length ?? 0} produtos cadastrados
          </p>
        </div>
        <Link to="/products/new">
          <Button>
            <Plus className="h-4 w-4" />
            Novo Produto
          </Button>
        </Link>
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
          <Button
            variant={filter === 'all' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter('all')}
          >
            Todos
          </Button>
          <Button
            variant={filter === 'GAS' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter('GAS')}
          >
            Gás
          </Button>
          <Button
            variant={filter === 'AGUA' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter('AGUA')}
          >
            Água
          </Button>
        </div>
      </div>

      {/* Product List */}
      {filteredProducts.length === 0 ? (
        <EmptyState
          icon={Package}
          title={search ? 'Nenhum produto encontrado' : 'Nenhum produto cadastrado'}
          description={
            search
              ? 'Nenhum produto corresponde aos filtros aplicados.'
              : 'Comece cadastrando seu primeiro produto.'
          }
          action={
            !search ? (
              <Link to="/products/new">
                <Button>
                  <Plus className="h-4 w-4" />
                  Cadastrar Produto
                </Button>
              </Link>
            ) : undefined
          }
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Lista de Produtos</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {filteredProducts.map((product) => (
                <Link
                  key={product.codigo}
                  to={`/products/${product.codigo}`}
                  className="flex items-center justify-between rounded-lg border border-border p-4 transition-colors hover:bg-accent/50"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-foreground">{product.nome}</p>
                      <Badge variant={product.tipo === 'GAS' ? 'info' : 'secondary'}>
                        {product.tipo === 'GAS' ? 'Gás' : 'Água'}
                      </Badge>
                      {!product.ativo && (
                        <Badge variant="secondary">Inativo</Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Código: {product.codigo} • Estoque: {product.estoque}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-foreground">
                      {formatCurrency(product.preco)}
                    </p>
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
