/**
 * Driver Form Page — Create/edit delivery drivers.
 * Uses existing /delivery-drivers/ endpoints.
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Save, Truck } from 'lucide-react'
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
  vehicle_type: string
}

export function DriverFormPage() {
  const { codigo } = useParams<{ codigo: string }>()
  const navigate = useNavigate()
  const isEdit = !!codigo

  const [formData, setFormData] = useState<DriverFormData>({
    nome: '',
    telefone: '',
    placa: '',
    vehicle_type: 'MOTORCYCLE',
  })
  const [fetching, setFetching] = useState(isEdit)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (isEdit && codigo) {
      setFetching(true)
      apiClient.get(`/delivery-drivers/${codigo}`)
        .then(({ data }) => {
          setFormData({
            nome: data.nome || '',
            telefone: data.telefone || '',
            placa: data.placa || '',
            vehicle_type: data.vehicle_type || 'MOTORCYCLE',
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
        await apiClient.put(`/delivery-drivers/${codigo}`, formData)
      } else {
        await apiClient.post('/delivery-drivers/', formData)
      }
      navigate('/drivers')
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
                <label htmlFor="vehicle_type" className="text-sm font-medium text-foreground">
                  Tipo de Veículo
                </label>
                <select
                  id="vehicle_type"
                  value={formData.vehicle_type}
                  onChange={(e) => setFormData({ ...formData, vehicle_type: e.target.value })}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
                >
                  <option value="MOTORCYCLE">Moto</option>
                  <option value="CAR">Carro</option>
                  <option value="VAN">Van</option>
                  <option value="TRUCK">Caminhão</option>
                </select>
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
