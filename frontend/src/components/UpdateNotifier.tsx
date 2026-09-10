import { useEffect, useState } from 'react'

interface UpdateState {
  status: 'idle' | 'checking' | 'available' | 'downloading' | 'ready' | 'error' | 'up-to-date'
  version: string | null
  progress: number
  error: string | null
}

interface GasflowUpdaterApi {
  check: () => Promise<{ ok: boolean; state?: UpdateState; error?: string }>
  install: () => Promise<{ ok: boolean; error?: string }>
  getState: () => Promise<UpdateState>
  onStateChange: (cb: (state: UpdateState) => void) => () => void
}

declare global {
  interface Window {
    gasflowUpdater?: GasflowUpdaterApi
  }
}

const MESSAGES: Record<string, string | ((s: UpdateState) => string)> = {
  checking: 'Verificando atualizações…',
  available: (s) => `Nova versão v${s.version} disponível. Baixando…`,
  downloading: (s) => `Baixando atualização… ${s.progress}%`,
  ready: (s) => `Versão v${s.version} pronta para instalar.`,
  error: () => 'Falha ao verificar atualizações (sem conexão ou release indisponível).',
}

/**
 * Notificação de auto-update — canto inferior direito.
 * Só renderiza dentro do Electron (window.gasflowUpdater existe) e apenas
 * quando há algo a dizer (checando / disponível / baixando / pronta / erro).
 */
export function UpdateNotifier() {
  const [state, setState] = useState<UpdateState>({ status: 'idle', version: null, progress: 0, error: null })

  useEffect(() => {
    const api = window.gasflowUpdater
    if (!api) return // rodando no navegador (dev) — sem auto-update
    let mounted = true
    api.getState().then((s) => { if (mounted) setState(s) }).catch(() => { /* main ainda não registrou */ })
    const off = api.onStateChange(setState)
    return () => { mounted = false; off() }
  }, [])

  if (state.status === 'idle' || state.status === 'up-to-date') return null

  const template = MESSAGES[state.status]
  const message = typeof template === 'function' ? template(state) : template

  const canInstall = state.status === 'ready'

  return (
    <div
      data-testid="update-notifier"
      className="fixed bottom-4 right-4 z-50 max-w-sm rounded-lg bg-slate-900 px-4 py-3 text-white shadow-lg"
    >
      <p className="text-sm">{message}</p>
      {state.status === 'downloading' && (
        <div className="mt-2 h-1 overflow-hidden rounded bg-slate-700">
          <div className="h-full bg-emerald-500 transition-all" style={{ width: `${state.progress}%` }} />
        </div>
      )}
      {canInstall && (
        <button
          onClick={() => window.gasflowUpdater?.install()}
          className="mt-2 rounded bg-emerald-600 px-3 py-1 text-sm hover:bg-emerald-500"
        >
          Reiniciar e instalar
        </button>
      )}
    </div>
  )
}

export default UpdateNotifier
