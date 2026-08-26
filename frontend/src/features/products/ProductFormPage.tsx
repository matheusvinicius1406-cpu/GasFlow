import { useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowLeft, Save } from 'lucide-react'
import { useProduct, useCreateProduct, useUpdateProduct } from '@/lib/api/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'

const productSchema = z.object({
  nome: z.string().min(1, 'Nome é obrigatório'),
  tipo: z.enum(['GAS', 'AGUA'], { required_error: 'Tipo é obrigatório' }),
  preco: z.number().min(0, 'Preço não pode ser negativo'),
  estoque: z.number().int().min(0, 'Estoque não pode ser negativo'),
})

type ProductFormData = z.infer<typeof productSchema>

export function ProductFormPage() {
  const { codigo } = useParams<{ codigo: string }>()
  const navigate = useNavigate()
  const isEdit = !!codigo

  const { data: product, isLoading: isLoadingProduct } = useProduct(codigo ?? '')
  const createProduct = useCreateProduct()
  const updateProduct = useUpdateProduct()

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<ProductFormData>({
    resolver: zodResolver(productSchema),
    defaultValues: {
      estoque: 0,
    },
  })

  useEffect(() => {
    if (product && isEdit) {
      reset({
        nome: product.nome,
        tipo: product.tipo as 'GAS' | 'AGUA',
        preco: product.preco,
        estoque: product.estoque,
      })
    }
  }, [product, isEdit, reset])

  const onSubmit = async (data: ProductFormData) => {
    try {
      if (isEdit && codigo) {
        await updateProduct.mutateAsync({ codigo, data })
        navigate(`/products/${codigo}`)
      } else {
        const created = await createProduct.mutateAsync(data)
        navigate(`/products/${created.codigo}`)
      }
    } catch {
      // Error handled by mutation
    }
  }

  if (isEdit && isLoadingProduct) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (isEdit && !product) {
    return (
      <ErrorState message="Produto não encontrado." onRetry={() => navigate('/products')} />
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <Link
            to="/products"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Link>
          <h1 className="text-2xl font-bold text-foreground">
            {isEdit ? 'Editar Produto' : 'Novo Produto'}
          </h1>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)}>
        <Card>
          <CardHeader>
            <CardTitle>Informações do Produto</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="nome" className="text-sm font-medium text-foreground">
                  Nome *
                </label>
                <Input
                  id="nome"
                  {...register('nome')}
                  placeholder="Ex: Gás P13, Água 20L"
                />
                {errors.nome && (
                  <p className="text-xs text-destructive">{errors.nome.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label htmlFor="tipo" className="text-sm font-medium text-foreground">
                  Tipo *
                </label>
                <select
                  id="tipo"
                  {...register('tipo')}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
                >
                  <option value="">Selecione o tipo</option>
                  <option value="GAS">Gás (GLP)</option>
                  <option value="AGUA">Água</option>
                </select>
                {errors.tipo && (
                  <p className="text-xs text-destructive">{errors.tipo.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label htmlFor="preco" className="text-sm font-medium text-foreground">
                  Preço (R$) *
                </label>
                <Input
                  id="preco"
                  type="number"
                  step="0.01"
                  {...register('preco', { valueAsNumber: true })}
                  placeholder="0.00"
                />
                {errors.preco && (
                  <p className="text-xs text-destructive">{errors.preco.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label htmlFor="estoque" className="text-sm font-medium text-foreground">
                  Estoque
                </label>
                <Input
                  id="estoque"
                  type="number"
                  {...register('estoque', { valueAsNumber: true })}
                  placeholder="0"
                />
                {errors.estoque && (
                  <p className="text-xs text-destructive">{errors.estoque.message}</p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="mt-6 flex justify-end gap-2">
          <Link to="/products">
            <Button type="button" variant="outline">
              Cancelar
            </Button>
          </Link>
          <Button type="submit" disabled={createProduct.isPending || updateProduct.isPending}>
            <Save className="h-4 w-4" />
            {createProduct.isPending || updateProduct.isPending
              ? 'Salvando...'
              : 'Salvar'}
          </Button>
        </div>
      </form>
    </div>
  )
}
