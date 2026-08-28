/**
 * Driver Login Page — GasFlow Driver App
 *
 * Mobile-friendly login for delivery drivers.
 * Uses /api/driver/v1/auth/login endpoint.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Truck, Lock, User } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'

export function DriverLoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) return

    setLoading(true)
    setError('')

    try {
      const response = await fetch('/api/driver/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })

      const data = await response.json()

      if (!response.ok || !data.success) {
        setError(data.error || 'Credenciais inválidas')
        return
      }

      // Store driver token
      localStorage.setItem('driver_token', data.token)
      localStorage.setItem('driver_id', data.driver_id)
      localStorage.setItem('driver_tenant', data.tenant_id)

      navigate('/driver')
    } catch {
      setError('Erro de conexão')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
            <Truck className="h-8 w-8 text-primary" />
          </div>
          <CardTitle className="text-2xl">GasFlow Motorista</CardTitle>
          <p className="text-sm text-muted-foreground">Faça login para acessar suas entregas</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            {error && (
              <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Usuário</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Nome ou telefone"
                  className="pl-10"
                  disabled={loading}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Senha</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Senha"
                  className="pl-10"
                  disabled={loading}
                />
              </div>
            </div>

            <Button type="submit" className="w-full" disabled={loading || !username || !password}>
              {loading ? <LoadingSpinner size="sm" /> : 'Entrar'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
