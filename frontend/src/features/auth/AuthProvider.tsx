import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
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

  useEffect(() => {
    // Check if token exists and validate
    if (token) {
      // For now, create a mock user if token exists
      // In production, this would call /api/auth/me
      setUser({
        id: '1',
        email: 'admin@gasflow.com',
        name: 'Administrador',
        role: 'ADMIN',
      })
    }
    setIsLoading(false)
  }, [token])

  const login = async (email: string, _password: string) => {
    // TODO: Replace with actual API call
    // const response = await api.auth.login(email, password)
    const mockUser: User = {
      id: '1',
      email,
      name: 'Administrador',
      role: 'ADMIN',
    }
    const mockToken = 'mock-jwt-token'

    localStorage.setItem('gasflow_token', mockToken)
    setToken(mockToken)
    setUser(mockUser)
  }

  const logout = () => {
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
