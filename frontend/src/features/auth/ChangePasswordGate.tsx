import { useState } from 'react'
import { useAuth } from './AuthProvider'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card } from '@/components/ui/Card'

/**
 * P0 (3.8): exibido pelo ProtectedRoute quando o login informa
 * must_change_password=true (reset de senha pelo admin). Nenhuma rota do
 * app é renderizada antes da troca — o backend só limpa a flag via
 * POST /auth/change-password (com a senha atual correta).
 */
const PASSWORD_PATTERN = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$/

export function ChangePasswordGate() {
  const { user, changePassword, logout } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const validate = (): string => {
    if (newPassword.length < 8) return 'A nova senha deve ter pelo menos 8 caracteres'
    if (!PASSWORD_PATTERN.test(newPassword)) {
      return 'A nova senha deve conter letra maiúscula, minúscula e número'
    }
    if (newPassword === currentPassword) return 'A nova senha deve ser diferente da atual'
    if (newPassword !== confirmPassword) return 'As senhas não coincidem'
    return ''
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }
    setIsLoading(true)
    try {
      await changePassword(currentPassword, newPassword)
      // Sucesso: a flag é limpa e o ProtectedRoute libera o app.
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Não foi possível alterar a senha')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md p-8">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-foreground">Troca de senha obrigatória</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {user?.name ? `${user.name}, s` : 'S'}ua senha foi redefinida por um administrador.
            Defina uma nova senha para continuar.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive" role="alert">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <label htmlFor="current-password" className="text-sm font-medium text-foreground">
              Senha atual
            </label>
            <Input
              id="current-password"
              type="password"
              placeholder="••••••••"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="new-password" className="text-sm font-medium text-foreground">
              Nova senha
            </label>
            <Input
              id="new-password"
              type="password"
              placeholder="••••••••"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              autoComplete="new-password"
            />
            <p className="text-xs text-muted-foreground">
              Mínimo de 8 caracteres, com maiúscula, minúscula e número.
            </p>
          </div>

          <div className="space-y-2">
            <label htmlFor="confirm-password" className="text-sm font-medium text-foreground">
              Confirmar nova senha
            </label>
            <Input
              id="confirm-password"
              type="password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
            />
          </div>

          <Button type="submit" className="w-full" disabled={isLoading}>
            {isLoading ? 'Salvando...' : 'Salvar nova senha'}
          </Button>
        </form>

        <button
          type="button"
          onClick={logout}
          className="mt-4 w-full text-center text-xs text-muted-foreground hover:text-foreground"
        >
          Entrar com outra conta
        </button>
      </Card>
    </div>
  )
}
