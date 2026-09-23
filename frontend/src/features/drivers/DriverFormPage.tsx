/**
 * Driver Form Page — Create/edit delivery drivers.
 *
 * Criar: `POST /admin/drivers` — caminho canônico, o único que cria a entidade
 * **e** a credencial de login, devolvendo a senha temporária (que aparece uma
 * vez, para o operador repassar ao entregador).
 *
 * Editar: `PUT /delivery-drivers/{codigo}` — só os campos editáveis. `codigo` é
 * imutável: é a identidade gravada em entregas, posições e histórico.
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, KeyRound, Save, Truck } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { apiClient } from '@/lib/api/client'

interface DriverFormData {
  nome: string
  telefone: string
  placa: string
  document: string
}

interface DriverCredentials {
  username: string
  password: string
}

export function DriverFormPage() {
  const { codigo } = useParams<{ codigo: string }>()
  const navigate = useNavigate()
  const isEdit = !!codigo

  const [formData, setFormData] = useState<DriverFormData>({
    nome: '',
    telefone: '',
    placa: '',
    document: '',
  })
  const [credentials, setCredentials] = useState<DriverCredentials | null>(null)
  const [fetching, setFetching] = useState(isEdit)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (isEdit && codigo) {
      setFetching(true)
      apiClient
        .get(`/delivery-drivers/${codigo}`)
        .then(({ data }) => {
          setFormData({
            nome: data.nome || '',
            telefone: data.telefone || '',
            placa: data.placa || '',
            document: data.document || '',
          })
        })
        .catch(() => setError('Motorista não encontrado'))
        .finally(() => setFetching(false))
    }
  }, [isEdit, codigo])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.nome.trim() || !formData.telefone.trim()) {
      setError('Nome e telefone são obrigatórios')
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      if (isEdit && codigo) {
        await apiClient.put(`/delivery-drivers/${codigo}`, {
          nome: formData.nome.trim(),
          telefone: formData.telefone.trim(),
          placa: formData.placa.trim() || null,
          document: formData.document.trim() || null,
        })
        navigate('/drivers')
      } else {
        // Canônico: cria o cadastro e a credencial na mesma transação.
        const { data } = await apiClient.post('/admin/drivers', {
          name: formData.nome.trim(),
          phone: formData.telefone.trim(),
          document: formData.document.trim() || null,
        })
        // A senha temporária só existe nesta resposta — não navegamos embora
        // antes de mostrá-la, senão ela se perde.
        if (data?.temporary_password) {
          setCredentials({ username: data.username ?? '', password: data.temporary_password })
        } else {
          navigate('/drivers')
        }
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Erro ao salvar motorista')
    } finally {
      setSubmitting(false)
    }
  }

  if (fetching) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error && isEdit && !formData.nome) {
    return <ErrorState message={error} onRetry={() => navigate('/drivers')} />
  }

  if (credentials) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-foreground">Motorista cadastrado</h1>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-5 w-5" />
              Credencial de acesso
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              A senha aparece <strong>uma única vez</strong>. Repasse ao entregador: no primeiro acesso o app exige a
              troca.
            </p>
            <div className="space-y-1">
              <span className="text-sm font-medium text-foreground">Usuário</span>
              <code
                data-testid="driver-username"
                className="block rounded-md bg-muted px-3 py-2 font-mono text-sm text-foreground"
              >
                {credentials.username}
              </code>
            </div>
            <div className="space-y-1">
              <span className="text-sm font-medium text-foreground">Senha temporária</span>
              <code
                data-testid="driver-temporary-password"
                className="block rounded-md bg-muted px-3 py-2 font-mono text-sm text-foreground"
              >
                {credentials.password}
              </code>
            </div>
            <div className="flex justify-end">
              <Button type="button" onClick={() => navigate('/drivers')}>
                Ir para a lista
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link
          to="/drivers"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Voltar
        </Link>
        <h1 className="text-2xl font-bold text-foreground">
          {isEdit ? 'Editar Motorista' : 'Novo Motorista'}
        </h1>
      </div>

      <form onSubmit={handleSubmit}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Truck className="h-5 w-5" />
              Dados do Motorista
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="nome" className="text-sm font-medium text-foreground">
                  Nome *
                </label>
                <Input
                  id="nome"
                  value={formData.nome}
                  onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                  placeholder="Nome do motorista"
                  required
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="telefone" className="text-sm font-medium text-foreground">
                  Telefone *
                </label>
                <Input
                  id="telefone"
                  value={formData.telefone}
                  onChange={(e) => setFormData({ ...formData, telefone: e.target.value })}
                  placeholder="(00) 00000-0000"
                  required
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="placa" className="text-sm font-medium text-foreground">
                  Placa
                </label>
                <Input
                  id="placa"
                  value={formData.placa}
                  onChange={(e) => setFormData({ ...formData, placa: e.target.value.toUpperCase() })}
                  placeholder="ABC-1234"
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="document" className="text-sm font-medium text-foreground">
                  CNH / Documento
                </label>
                <Input
                  id="document"
                  value={formData.document}
                  onChange={(e) => setFormData({ ...formData, document: e.target.value })}
                  placeholder="000.000.000-00"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="mt-6 flex justify-end gap-2">
          <Link to="/drivers">
            <Button type="button" variant="outline">
              Cancelar
            </Button>
          </Link>
          <Button type="submit" disabled={submitting}>
            <Save className="h-4 w-4" />
            {submitting ? 'Salvando...' : 'Salvar'}
          </Button>
        </div>
      </form>
    </div>
  )
}
