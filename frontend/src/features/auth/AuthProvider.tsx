import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { api } from '@/lib/api/client'
import type { User } from '@/types'

export interface AuthContextType {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  isLoading: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(localStorage.getItem('gasflow_token'))
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
    } catch {
      // Token invalid — clear
      localStorage.removeItem('gasflow_token')
      setToken(null)
      setUser(null)
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
      throw new Error(msg || 'Credenciais inválidas')
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
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token && !!user,
        login,
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
  const { isAuthenticated, isLoading } = useAuth()

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

  return <>{children}</>
}
