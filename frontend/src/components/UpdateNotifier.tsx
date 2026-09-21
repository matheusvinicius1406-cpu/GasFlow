import { useCallback, useState } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { useUpdaterState } from '@/lib/update/updater'

/**
 * Aviso de canto (inferior direito) do auto-update.
 *
 * Cobre só o que exige pouca atenção — "verificando" e "erro". Os estados com
 * progresso (`available`/`downloading`) e a decisão de reiniciar (`ready`) são
 * do `UpdateScreen`, que reparte os estados justamente para não duplicar aviso.
 * Só renderiza dentro do Electron (`window.gasflowUpdater` existe).
 */
export function UpdateNotifier() {
  const state = useUpdaterState()
  const [retrying, setRetrying] = useState(false)

  /** Refaz a verificação sob demanda (`update:check`) — saída para o erro. */
  const retry = useCallback(async () => {
    const api = window.gasflowUpdater
    if (!api) return
    setRetrying(true)
    try {
      await api.check()
    } finally {
      // O estado que vier do main (checking/available/error) assume daqui.
      setRetrying(false)
    }
  }, [])

  if (state.status !== 'checking' && state.status !== 'error') return null

  const isError = state.status === 'error'
  const busy = retrying || state.status === 'checking'

  return (
    <div
      data-testid="update-notifier"
      role="status"
      aria-live="polite"
      className="gf-anim-rise-in fixed bottom-4 right-4 z-50 max-w-sm rounded-lg border border-border bg-card px-4 py-3 shadow-lg"
    >
      <p className="flex items-center gap-2 text-sm text-foreground">
        {isError && !busy ? (
          <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
        ) : (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />
        )}
        {isError && !busy
          ? 'Falha ao verificar atualizações (sem conexão ou release indisponível).'
          : 'Verificando atualizações…'}
      </p>

      {isError && !busy && (
        <Button variant="outline" size="sm" className="mt-2 w-full" onClick={retry}>
          Tentar novamente
        </Button>
      )}
    </div>
  )
}

export default UpdateNotifier
