import { useState, useEffect, useCallback } from 'react'
import { Settings, User, Shield, RefreshCw, CreditCard, SlidersHorizontal, Users } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { apiClient } from '@/lib/api/client'
import { useAuth } from '@/features/auth'
import { PaymentSettingsPage } from './PaymentSettingsPage'
import { SystemSettingsPanel } from './SystemSettingsPanel'
import { PermissionsPanel } from './PermissionsPanel'

interface UserProfile {
  id: string
  username: string
  email: string
  display_name: string
  status: string
  tenant_id: string
  role: string
  permissions: string[]
}

export function SettingsPage() {
  const { logout } = useAuth()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [activeTab, setActiveTab] = useState<
    'profile' | 'payments' | 'system' | 'permissions'
  >('profile')

  const fetchProfile = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await apiClient.get('/auth/me')
      setProfile(data)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchProfile() }, [fetchProfile])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <ErrorState
        message="Não foi possível carregar as configurações."
        onRetry={fetchProfile}
      />
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Configurações</h1>
          <p className="text-muted-foreground">Perfil e informações do sistema</p>
        </div>
        <Button onClick={fetchProfile} variant="outline">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b pb-2">
        <Button variant={activeTab === 'profile' ? 'default' : 'ghost'} onClick={() => setActiveTab('profile')}>
          <User className="h-4 w-4 mr-1" /> Perfil
        </Button>
        <Button variant={activeTab === 'payments' ? 'default' : 'ghost'} onClick={() => setActiveTab('payments')}>
          <CreditCard className="h-4 w-4 mr-1" /> Pagamentos
        </Button>
        <Button variant={activeTab === 'system' ? 'default' : 'ghost'} onClick={() => setActiveTab('system')}>
          <SlidersHorizontal className="h-4 w-4 mr-1" /> Sistema
        </Button>
        <Button variant={activeTab === 'permissions' ? 'default' : 'ghost'} onClick={() => setActiveTab('permissions')}>
          <Users className="h-4 w-4 mr-1" /> Usuários e Permissões
        </Button>
      </div>

      {activeTab === 'payments' ? (
        <PaymentSettingsPage />
      ) : activeTab === 'system' ? (
        <SystemSettingsPanel />
      ) : activeTab === 'permissions' ? (
        <PermissionsPanel />
      ) : (
        <>
          {/* User Profile */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <User className="h-5 w-5" />
                Perfil do Usuário
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {profile && (
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="text-sm text-muted-foreground">Nome</p>
                    <p className="font-medium text-foreground">{profile.display_name}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Usuário</p>
                    <p className="font-medium text-foreground">{profile.username}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Email</p>
                    <p className="font-medium text-foreground">{profile.email}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Status</p>
                    <Badge variant={profile.status === 'ACTIVE' ? 'success' : 'secondary'}>
                      {profile.status === 'ACTIVE' ? 'Ativo' : profile.status}
                    </Badge>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Security */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5" />
                Segurança
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {profile && (
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="text-sm text-muted-foreground">Tenant</p>
                    <p className="font-medium text-foreground">{profile.tenant_id}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Função</p>
                    <Badge variant="outline">{profile.role}</Badge>
                  </div>
                  <div className="md:col-span-2">
                    <p className="text-sm text-muted-foreground">Permissões</p>
                    <div className="flex flex-wrap gap-2 mt-1">
                      {profile.permissions.map((perm) => (
                        <Badge key={perm} variant="secondary" className="text-xs">
                          {perm}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              <div className="border-t border-border pt-4">
                <Button variant="destructive" onClick={logout}>
                  Sair da conta
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* System Info */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Sistema
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <p className="text-sm text-muted-foreground">Versão</p>
                  <p className="font-medium text-foreground">0.1.0</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Arquitetura</p>
                  <p className="font-medium text-foreground">Domain-Driven Design (DDD)</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
