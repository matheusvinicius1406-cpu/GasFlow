import { useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowLeft, Save } from 'lucide-react'
import { useCustomer, useCreateCustomer, useUpdateCustomer } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'

const customerSchema = z.object({
  nome: z.string().min(1, 'Nome é obrigatório'),
  telefone: z.string().min(1, 'Telefone é obrigatório'),
  telefone_secundario: z.string().optional(),
  rua: z.string().min(1, 'Rua é obrigatória'),
  numero: z.string().min(1, 'Número é obrigatório'),
  complemento: z.string().optional(),
  referencia: z.string().optional(),
  bairro: z.string().min(1, 'Bairro é obrigatório'),
  observacoes: z.string().optional(),
  tipo: z.string().optional(),
  email: z.string().optional(),
})

type CustomerFormData = z.infer<typeof customerSchema>

export function CustomerFormPage() {
  const { codigo } = useParams<{ codigo: string }>()
  const navigate = useNavigate()
  const isEdit = !!codigo

  const { data: customer, isLoading: isLoadingCustomer } = useCustomer(codigo ?? '')
  const createCustomer = useCreateCustomer()
  const updateCustomer = useUpdateCustomer()

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<CustomerFormData>({
    resolver: zodResolver(customerSchema),
  })

  useEffect(() => {
    if (customer && isEdit) {
      reset({
        nome: customer.nome,
        telefone: customer.telefone,
        telefone_secundario: customer.telefone_secundario ?? '',
        rua: customer.rua,
        numero: customer.numero,
        complemento: customer.complemento ?? '',
        referencia: customer.referencia ?? '',
        bairro: customer.bairro,
        observacoes: customer.observacoes ?? '',
        tipo: customer.tipo ?? '',
        email: customer.email ?? '',
      })
    }
  }, [customer, isEdit, reset])

  const onSubmit = async (data: CustomerFormData) => {
    try {
      if (isEdit && codigo) {
        await updateCustomer.mutateAsync({ codigo, data })
        navigate(`/customers/${codigo}`)
      } else {
        const created = await createCustomer.mutateAsync(data)
        navigate(`/customers/${created.codigo}`)
      }
    } catch {
      // Error handled by mutation
    }
  }

  if (isEdit && isLoadingCustomer) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (isEdit && !customer) {
    return (
      <ErrorState message="Cliente não encontrado." onRetry={() => navigate('/customers')} />
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <Link
            to="/customers"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Link>
          <h1 className="text-2xl font-bold text-foreground">
            {isEdit ? 'Editar Cliente' : 'Novo Cliente'}
          </h1>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)}>
        <Card>
          <CardHeader>
            <CardTitle>Dados Pessoais</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="nome" className="text-sm font-medium text-foreground">
                  Nome *
                </label>
                <Input id="nome" {...register('nome')} placeholder="Nome do cliente" />
                {errors.nome && (
                  <p className="text-xs text-destructive">{errors.nome.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label htmlFor="telefone" className="text-sm font-medium text-foreground">
                  Telefone *
                </label>
                <Input
                  id="telefone"
                  {...register('telefone')}
                  placeholder="(00) 00000-0000"
                />
                {errors.telefone && (
                  <p className="text-xs text-destructive">{errors.telefone.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label
                  htmlFor="telefone_secundario"
                  className="text-sm font-medium text-foreground"
                >
                  Telefone Secundário
                </label>
                <Input
                  id="telefone_secundario"
                  {...register('telefone_secundario')}
                  placeholder="(00) 00000-0000"
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="tipo" className="text-sm font-medium text-foreground">
                  Tipo
                </label>
                <select
                  id="tipo"
                  {...register('tipo')}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                >
                  <option value="">Selecione...</option>
                  <option value="CONSUMER">Consumidor</option>
                  <option value="RESTAURANT">Restaurante</option>
                  <option value="COMPANY">Empresa</option>
                  <option value="SCHOOL">Escola</option>
                  <option value="OTHER">Outro</option>
                </select>
              </div>

              <div className="space-y-2">
                <label htmlFor="email" className="text-sm font-medium text-foreground">
                  Email
                </label>
                <Input
                  id="email"
                  {...register('email')}
                  placeholder="email@exemplo.com"
                  type="email"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Endereço</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="rua" className="text-sm font-medium text-foreground">
                  Rua *
                </label>
                <Input id="rua" {...register('rua')} placeholder="Nome da rua" />
                {errors.rua && (
                  <p className="text-xs text-destructive">{errors.rua.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label htmlFor="numero" className="text-sm font-medium text-foreground">
                  Número *
                </label>
                <Input id="numero" {...register('numero')} placeholder="Número" />
                {errors.numero && (
                  <p className="text-xs text-destructive">{errors.numero.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label htmlFor="bairro" className="text-sm font-medium text-foreground">
                  Bairro *
                </label>
                <Input id="bairro" {...register('bairro')} placeholder="Bairro" />
                {errors.bairro && (
                  <p className="text-xs text-destructive">{errors.bairro.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label
                  htmlFor="complemento"
                  className="text-sm font-medium text-foreground"
                >
                  Complemento
                </label>
                <Input
                  id="complemento"
                  {...register('complemento')}
                  placeholder="Complemento"
                />
              </div>

              <div className="space-y-2">
                <label
                  htmlFor="referencia"
                  className="text-sm font-medium text-foreground"
                >
                  Referência
                </label>
                <Input
                  id="referencia"
                  {...register('referencia')}
                  placeholder="Ponto de referência"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label
                htmlFor="observacoes"
                className="text-sm font-medium text-foreground"
              >
                Observações
              </label>
              <Input
                id="observacoes"
                {...register('observacoes')}
                placeholder="Observações sobre o cliente"
              />
            </div>
          </CardContent>
        </Card>

        <div className="mt-6 flex justify-end gap-2">
          <Link to="/customers">
            <Button type="button" variant="outline">
              Cancelar
            </Button>
          </Link>
          <Button type="submit" disabled={createCustomer.isPending || updateCustomer.isPending}>
            <Save className="h-4 w-4" />
            {createCustomer.isPending || updateCustomer.isPending
              ? 'Salvando...'
              : 'Salvar'}
          </Button>
        </div>
      </form>
    </div>
  )
}
