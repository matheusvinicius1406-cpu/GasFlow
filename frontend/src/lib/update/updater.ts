import { useEffect, useState } from 'react'

/**
 * Ponte de auto-update exposta pelo preload do Electron
 * (`desktop/src/preload/index.ts` → canais `updater:*`).
 *
 * Fora do Electron (`window.gasflowUpdater` ausente — dev no navegador, web
 * hospedada), o estado fica permanentemente `idle` e nenhuma tela de
 * atualização aparece. É a única fonte de verdade do estado de update: tanto
 * o banner/overlay (`UpdateScreen`) quanto o aviso de canto
 * (`UpdateNotifier`) leem daqui.
 */
export type UpdateStatus =
  | 'idle'
  | 'checking'
  | 'available'
  | 'downloading'
  | 'ready'
  | 'error'
  | 'up-to-date'

export interface UpdateState {
  status: UpdateStatus
  /** Versão que está sendo oferecida/baixada (`null` enquanto não se sabe). */
  version: string | null
  /** Percentual do download (0–100). */
  progress: number
  error: string | null
}

export interface GasflowUpdaterApi {
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

export const INITIAL_UPDATE_STATE: UpdateState = {
  status: 'idle',
  version: null,
  progress: 0,
  error: null,
}

/**
 * Assina o estado do auto-update do processo main. Sem a ponte (fora do
 * Electron) devolve sempre `idle`.
 */
export function useUpdaterState(): UpdateState {
  const [state, setState] = useState<UpdateState>(INITIAL_UPDATE_STATE)

  useEffect(() => {
    const api = window.gasflowUpdater
    if (!api) return

    let mounted = true
    api
      .getState()
      .then((s) => {
        if (mounted) setState(s)
      })
      .catch(() => {
        /* main ainda não registrou o handler — fica em idle */
      })

    const unsubscribe = api.onStateChange((s) => setState(s))
    return () => {
      mounted = false
      unsubscribe()
    }
  }, [])

  return state
}
