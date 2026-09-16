import { useCallback, useEffect, useState } from 'react'
import { Ticket } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { apiClient } from '@/lib/api/client'
import { formatDate, formatCurrency } from '@/lib/utils'

interface ClientCoupon {
  id: string
  code: string
  type: string
  value: number | null
  end_date: string | null
  is_referral: boolean
  status: 'active' | 'used' | 'expired'
}

function formatValue(c: ClientCoupon): string {
  if (c.type === 'PERCENTAGE') return `${c.value ?? 0}%`
  if (c.type === 'FIXED') return formatCurrency(c.value ?? 0)
  return 'Frete grátis'
}

const STATUS_LABELS: Record<string, { label: string; variant: 'success' | 'secondary' | 'destructive' }> = {
  active: { label: 'Ativo', variant: 'success' },
  used: { label: 'Usado', variant: 'secondary' },
  expired: { label: 'Expirado', variant: 'destructive' },
}

export function ClientCouponsTab({ clientCodigo }: { clientCodigo: string }) {
  const [coupons, setCoupons] = useState<ClientCoupon[]>([])
  const [loading, setLoading] = useState(true)

  const fetchCoupons = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await apiClient.get(`/coupons/by-client/${clientCodigo}`)
      setCoupons(data.items ?? [])
    } catch {
      setCoupons([])
    } finally {
      setLoading(false)
    }
  }, [clientCodigo])

  useEffect(() => {
    fetchCoupons()
  }, [fetchCoupons])

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  if (coupons.length === 0) {
    return (
      <EmptyState
        icon={Ticket}
        title="Nenhum cupom"
        description="Este cliente não possui cupons."
      />
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cupons ({coupons.length})</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="pb-2 pr-4">Código</th>
                <th className="pb-2 pr-4">Desconto</th>
                <th className="pb-2 pr-4">Validade</th>
                <th className="pb-2 pr-4">Tipo</th>
                <th className="pb-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {coupons.map((c) => (
                <tr key={c.id} className="border-b last:border-0">
                  <td className="py-2 pr-4 font-mono font-medium">{c.code}</td>
                  <td className="py-2 pr-4">{formatValue(c)}</td>
                  <td className="py-2 pr-4">{c.end_date ? formatDate(c.end_date) : '—'}</td>
                  <td className="py-2 pr-4">
                    {c.is_referral && <Badge variant="outline">Indicação</Badge>}
                  </td>
                  <td className="py-2">
                    <Badge variant={STATUS_LABELS[c.status]?.variant ?? 'secondary'}>
                      {STATUS_LABELS[c.status]?.label ?? c.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
