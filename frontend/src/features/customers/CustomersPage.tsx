import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Users, Plus, Search, Phone, ChevronLeft, ChevronRight } from 'lucide-react'
import { useCustomers } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatPhone } from '@/lib/utils'

const CLIENT_TYPES = [
  { value: '', label: 'Todos os tipos' },
  { value: 'CONSUMER', label: 'Consumidor' },
  { value: 'RESTAURANT', label: 'Restaurante' },
  { value: 'COMPANY', label: 'Empresa' },
  { value: 'SCHOOL', label: 'Escola' },
  { value: 'OTHER', label: 'Outro' },
]

export function CustomersPage() {
  const [search, setSearch] = useState('')
  const [tipo, setTipo] = useState('')
  const [filter, setFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [page, setPage] = useState(1)
  const pageSize = 20

  const ativoFilter = filter === 'active' ? true : filter === 'inactive' ? false : undefined

  const { data, isLoading, error, refetch } = useCustomers({
    q: search || undefined,
    tipo: tipo || undefined,
    ativo: ativoFilter,
    page,
    page_size: pageSize,
  })

  const customers = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 0

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
        message="Não foi possível carregar os clientes."
        onRetry={() => refetch()}
      />
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Clientes</h1>
          <p className="text-muted-foreground">
            {total} clientes cadastrados
          </p>
        </div>
        <Link to="/customers/new">
          <Button>
            <Plus className="h-4 w-4" />
            Novo Cliente
          </Button>
        </Link>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Buscar por nome, código, telefone ou bairro..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="pl-10"
          />
        </div>
        <div className="flex gap-2">
          <select
            value={tipo}
            onChange={(e) => { setTipo(e.target.value); setPage(1) }}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm"
          >
            {CLIENT_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <Button
            variant={filter === 'all' ? 'default' : 'outline'}
            size="sm"
            onClick={() => { setFilter('all'); setPage(1) }}
          >
            Todos
          </Button>
          <Button
            variant={filter === 'active' ? 'default' : 'outline'}
            size="sm"
            onClick={() => { setFilter('active'); setPage(1) }}
          >
            Ativos
          </Button>
          <Button
            variant={filter === 'inactive' ? 'default' : 'outline'}
            size="sm"
            onClick={() => { setFilter('inactive'); setPage(1) }}
          >
            Inativos
          </Button>
        </div>
      </div>

      {/* Customer List */}
      {customers.length === 0 ? (
        <EmptyState
          icon={Users}
          title={search ? 'Nenhum cliente encontrado' : 'Nenhum cliente cadastrado'}
          description={
            search
              ? 'Nenhum cliente corresponde aos filtros aplicados.'
              : 'Comece cadastrando seu primeiro cliente.'
          }
          action={
            !search ? (
              <Link to="/customers/new">
                <Button>
                  <Plus className="h-4 w-4" />
                  Cadastrar Cliente
                </Button>
              </Link>
            ) : undefined
          }
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Lista de Clientes</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {customers.map((customer) => (
                <Link
                  key={customer.codigo}
                  to={`/customers/${customer.codigo}`}
                  className="flex items-center justify-between rounded-lg border border-border p-4 transition-colors hover:bg-accent/50"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-foreground">{customer.nome}</p>
                      <Badge variant={customer.ativo ? 'success' : 'secondary'}>
                        {customer.ativo ? 'Ativo' : 'Inativo'}
                      </Badge>
                      {customer.tipo && (
                        <Badge variant="outline">
                          {CLIENT_TYPES.find(t => t.value === customer.tipo)?.label ?? customer.tipo}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Código: {customer.codigo} • {customer.bairro}
                    </p>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Phone className="h-3 w-3" />
                      {formatPhone(customer.telefone)}
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">
                      {customer.rua}, {customer.numero}
                    </p>
                  </div>
                </Link>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-4 flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  Página {page} de {totalPages}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page <= 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Anterior
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                  >
                    Próxima
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
