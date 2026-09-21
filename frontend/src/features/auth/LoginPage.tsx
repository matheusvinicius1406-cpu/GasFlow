import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from './AuthProvider'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card } from '@/components/ui/Card'
import { BrandLogo, BrandName } from '@/components/brand/BrandLogo'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      await login(email, password)
      navigate('/')
    } catch {
      setError('Email ou senha inválidos')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background p-4">
      {/*
        Brilhos de fundo: derivam devagar atrás do cartão. Só CSS e tokens do
        design system (nada de imagem), então acompanham o tema do cliente.
      */}
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <span className="gf-anim-drift absolute -left-16 -top-24 h-72 w-72 rounded-full bg-primary/10 blur-3xl" />
        <span className="gf-anim-drift-slow absolute -bottom-24 -right-10 h-80 w-80 rounded-full bg-primary/10 blur-3xl" />
      </div>

      <Card className="gf-anim-rise-in relative w-full max-w-md p-8">
        {/*
          Entrada em cascata: marca → título → campos. O splash do boot
          (index.html) dissolve no mesmo instante em que isto monta, então a
          abertura do app termina aqui em vez de num corte seco.
        */}
        <div className="mb-8 text-center">
          <div className="relative mx-auto mb-4 flex h-14 w-14 items-center justify-center">
            <span
              aria-hidden
              className="gf-anim-pulse-ring absolute inset-0 rounded-2xl bg-primary/20"
            />
            <span className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 ring-1 ring-primary/20">
              <BrandLogo size="lg" />
            </span>
          </div>
          <BrandName size="lg" showTagline className="gf-anim-rise-in gf-anim-delay-1 items-center" />
          <p className="gf-anim-rise-in gf-anim-delay-2 mt-2 text-sm text-muted-foreground">
            Sistema operacional para revendas de gás
          </p>
        </div>

        <form onSubmit={handleSubmit} className="gf-anim-rise-in gf-anim-delay-3 space-y-4">
          {error && (
            <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <label htmlFor="email" className="text-sm font-medium text-foreground">
              Usuário
            </label>
            <Input
              id="email"
              type="text"
              placeholder="admin"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="username"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="password" className="text-sm font-medium text-foreground">
              Senha
            </label>
            <Input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <Button type="submit" className="w-full" disabled={isLoading}>
            {isLoading ? 'Entrando...' : 'Entrar'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
