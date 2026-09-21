import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { api } from '@/lib/api/client'
import type { User } from '@/types'
import { ChangePasswordGate } from './ChangePasswordGate'

/**
 * P0 3.6: ponte Electron (window.gasflow do preload), quando roda no desktop.
 * O main process valida permissões de handlers IPC nativos consultando
 * /auth/me com o token da sessão — report login/logout/change-password.
 */
function electronSessionBridge() {
  return (
    window as unknown as {
      gasflow?: {
        reportSessionToken?: (token: string) => Promise<unknown>
        notifySessionChanged?: () => Promise<unknown>
      }
    }
  ).gasflow
}

export interface AuthContextType {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  /** Permissões efetivas do usuário (do backend — nunca hardcode no frontend). */
  permissions: string[]
  hasPermission: (permission: string) => boolean
  /** P0 (3.8): true pós-reset admin — o app fica bloqueado até a troca. */
  mustChangePassword: boolean
  login: (email: string, password: string) => Promise<void>
  /** Troca self-service; ao sucesso, desbloqueia o app sem novo login. */
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
  logout: () => void
  isLoading: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(localStorage.getItem('gasflow_token'))
  const [permissions, setPermissions] = useState<string[]>([])
  const [mustChangePassword, setMustChangePassword] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  const fetchMe = useCallback(async () => {
    try {
      const res = await api.auth.me()
      const data = res.data
      setUser({
        id: data.id,
        email: data.email || data.username,
        name: data.display_name || data.username,
        role: data.role || 'OPERATOR',
      })
      setPermissions(Array.isArray(data.permissions) ? data.permissions : [])
      setMustChangePassword(Boolean(data.must_change_password))
      // Sessão restaurada do localStorage → repassa o token ao gate IPC.
      const stored = localStorage.getItem('gasflow_token')
      if (stored) void electronSessionBridge()?.reportSessionToken?.(stored)
    } catch {
      // Token invalid — clear
      localStorage.removeItem('gasflow_token')
      setToken(null)
      setUser(null)
      setPermissions([])
      setMustChangePassword(false)
    }
  }, [])

  useEffect(() => {
    if (token) {
      fetchMe().finally(() => setIsLoading(false))
    } else {
      setIsLoading(false)
    }
  }, [token, fetchMe])

  const login = async (email: string, password: string) => {
    let data
    try {
      const res = await api.auth.login(email, password)
      data = res.data
    } catch (err: unknown) {
      // Axios error from 401 response
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      throw new Error(msg || 'Credenciais inválidas', { cause: err })
    }

    if (!data?.success) {
      throw new Error(data?.error || 'Credenciais inválidas')
    }

    localStorage.setItem('gasflow_token', data.token)
    setToken(data.token)
    setUser({
      id: data.user?.id || '',
      email: data.user?.email || email,
      name: data.user?.display_name || data.user?.username || email,
      role: (data.role as User['role']) || 'OPERATOR',
    })
    // P0 (3.8): reset admin seta a flag — o cliente bloqueia o app até a troca.
    setMustChangePassword(Boolean(data.user?.must_change_password))
    // P0 (3.6): token novo → gate IPC de permissões no main process.
    void electronSessionBridge()?.reportSessionToken?.(data.token)
    // Permissões chegam no próximo fetchMe — busca imediata para a sessão.
    try {
      const me = await api.auth.me()
      setPermissions(Array.isArray(me.data.permissions) ? me.data.permissions : [])
    } catch {
      setPermissions([])
    }
  }

  const logout = async () => {
    try {
      await api.auth.logout()
    } catch {
      // Ignore — local logout still happens
    }
    localStorage.removeItem('gasflow_token')
    setToken(null)
    setUser(null)
    setPermissions([])
    setMustChangePassword(false)
    // P0 (3.6): invalida o cache de permissões do gate IPC.
    void electronSessionBridge()?.notifySessionChanged?.()
  }

  // P0 (3.8): troca obrigatória — no sucesso o backend limpa a flag e o app desbloqueia.
  const changePassword = async (currentPassword: string, newPassword: string) => {
    try {
      await api.auth.changePassword(currentPassword, newPassword)
      setMustChangePassword(false)
      // P0 (3.6): senha trocada → refetch de permissões no gate IPC.
      void electronSessionBridge()?.notifySessionChanged?.()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      throw new Error(msg || 'Não foi possível alterar a senha', { cause: err })
    }
  }

  // admin.* concede tudo (mesma semântica do backend TenantContext).
  const hasPermission = useCallback(
    (permission: string) => {
      if (permissions.includes('admin.*')) return true
      if (permissions.includes(permission)) return true
      // Wildcard por módulo: inventory.* cobre inventory.adjust.
      const resource = permission.split('.')[0]
      return permissions.includes(`${resource}.*`)
    },
    [permissions]
  )

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token && !!user,
        permissions,
        hasPermission,
        mustChangePassword,
        login,
        changePassword,
        logout,
        isLoading,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, mustChangePassword } = useAuth()

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  // P0 (3.8): senha provisória (reset admin) — nenhuma rota do app é acessível
  // antes da troca. Sem logout, para não contornar via re-login.
  if (mustChangePassword) {
    return <ChangePasswordGate />
  }

  return <>{children}</>
}

/** Guard por permissão: redireciona ao dashboard se não tem nenhuma delas. */
export function PermissionRoute({
  permissions,
  children,
}: {
  permissions: string[]
  children: ReactNode
}) {
  const { hasPermission, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    )
  }

  if (!permissions.some((p) => hasPermission(p))) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
