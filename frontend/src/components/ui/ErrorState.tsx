import { AlertTriangle } from 'lucide-react'
import { failureTitle } from '@/lib/api/failure'
import { cn } from '@/lib/utils'
import { Button } from './Button'

interface ErrorStateProps {
  title?: string
  message: string
  onRetry?: () => void
  className?: string
  /** Falha que originou o estado — 403 vira "Sem permissão", falha de rede
   *  vira "Sem conexão", o resto mantém o título genérico. */
  error?: unknown
}

export function ErrorState({
  title,
  message,
  onRetry,
  className,
  error,
}: ErrorStateProps) {
  const heading = title ?? failureTitle(error)
  return (
    <div className={cn('flex flex-col items-center justify-center py-12 text-center', className)}>
      <div className="rounded-full bg-destructive/10 p-4">
        <AlertTriangle className="h-8 w-8 text-destructive" />
      </div>
      <h3 className="mt-4 text-lg font-semibold text-foreground">{heading}</h3>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">{message}</p>
      {onRetry && (
        <div className="mt-6">
          <Button variant="outline" onClick={onRetry}>
            Tentar novamente
          </Button>
        </div>
      )}
    </div>
  )
}
