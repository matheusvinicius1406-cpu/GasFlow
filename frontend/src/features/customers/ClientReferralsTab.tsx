import { useCallback, useEffect, useState } from 'react'
import { Users } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { apiClient } from '@/lib/api/client'
import { formatDate } from '@/lib/utils'

interface Referral {
  id: string
  invite_token: string
  referred_name: string | null
  referred_client_codigo: string | null
  created_at: string | null
  completed: boolean
}

export function ClientReferralsTab({ clientCodigo }: { clientCodigo: string }) {
  const [referrals, setReferrals] = useState<Referral[]>([])
  const [loading, setLoading] = useState(true)
  const [meta, setMeta] = useState({ total: 0, completed: 0, pending: 0, monthly_limit: 10 })

  const fetchReferrals = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await apiClient.get(`/coupons/by-client/${clientCodigo}/referrals`)
      setReferrals(data.items ?? [])
      setMeta({
        total: data.total ?? 0,
        completed: data.completed ?? 0,
        pending: data.pending ?? 0,
        monthly_limit: data.monthly_limit ?? 10,
      })
    } catch {
      setReferrals([])
    } finally {
      setLoading(false)
    }
  }, [clientCodigo])

  useEffect(() => {
    fetchReferrals()
  }, [fetchReferrals])

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Indicações</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-4 text-sm">
          <span>Total: <strong>{meta.total}</strong></span>
          <span>Concluídas: <strong>{meta.completed}</strong></span>
          <span>Pendentes: <strong>{meta.pending}</strong></span>
          <span>Limite mensal: <strong>{meta.monthly_limit}</strong></span>
        </div>

        {referrals.length === 0 ? (
          <EmptyState
            icon={Users}
            title="Nenhuma indicação"
            description="Este cliente ainda não fez indicações."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 pr-4">Indicado</th>
                  <th className="pb-2 pr-4">Código</th>
                  <th className="pb-2 pr-4">Data</th>
                  <th className="pb-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {referrals.map((r) => (
                  <tr key={r.id} className="border-b last:border-0">
                    <td className="py-2 pr-4">{r.referred_name || '—'}</td>
                    <td className="py-2 pr-4 font-mono text-xs">{r.referred_client_codigo || '—'}</td>
                    <td className="py-2 pr-4">{r.created_at ? formatDate(r.created_at) : '—'}</td>
                    <td className="py-2">
                      <Badge variant={r.completed ? 'success' : 'secondary'}>
                        {r.completed ? 'Concluída' : 'Pendente'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
