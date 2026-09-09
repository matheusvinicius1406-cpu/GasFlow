import { useCallback, useEffect, useState } from 'react'
import { Users, ShieldCheck } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { apiClient } from '@/lib/api/client'

interface MatrixResponse {
  roles: Record<string, string[]>
  me: { role: string; permissions: string[] }
}

export function PermissionsPanel() {
  const [matrix, setMatrix] = useState<MatrixResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchMatrix = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await apiClient.get<MatrixResponse>('/settings/permissions/matrix')
      setMatrix(data)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchMatrix()
  }, [fetchMatrix])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error || !matrix) {
    return <ErrorState message="Não foi possível carregar a matriz de permissões." onRetry={fetchMatrix} />
  }

  const roles = Object.entries(matrix.roles)

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Usuários e Permissões</h3>
        <p className="text-sm text-muted-foreground">
          Matriz de permissões por função (RBAC). Suas permissões efetivas: <Badge variant="outline">{matrix.me.role}</Badge>
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {matrix.me.permissions.map((perm) => (
          <Badge key={perm} variant="secondary" className="text-xs font-mono">
            {perm}
          </Badge>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {roles.map(([role, perms]) => (
          <Card key={role}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                {role === matrix.me.role ? <ShieldCheck className="h-5 w-5 text-primary" /> : <Users className="h-5 w-5" />}
                {role}
                {role === matrix.me.role && <Badge variant="default">você</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1.5">
                {perms.map((perm) => (
                  <Badge key={perm} variant="secondary" className="text-xs font-mono">
                    {perm}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
