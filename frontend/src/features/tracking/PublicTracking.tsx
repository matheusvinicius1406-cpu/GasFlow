/**
 * PublicTracking — página pública de acompanhamento (Fase 7.2).
 *
 * Rota `/track/:token`, **sem menu e sem login**. O token (emitido por
 * operador/admin) carrega tenant + driver + expiração; a resposta não tem PII.
 *
 * Usa `fetch` cru de propósito: o `apiClient` trata 401 com renovação de sessão
 * e redirect — aqui um 401 do link é o esperado ("link expirado"), não um
 * problema de sessão.
 */
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, MapPin, ShieldAlert } from 'lucide-react'
import { DriverMap, type DriverMapPoint } from '@/components/map/DriverMap'

const REFRESH_MS = 30_000

interface PublicSnapshot {
  driver_id: string
  latitude: number
  longitude: number
  updated_at: string | null
}

type State =
  | { status: 'loading' }
  | { status: 'ok'; snapshot: PublicSnapshot }
  | { status: 'expired' }
  | { status: 'missing' }
  | { status: 'error' }

export function PublicTracking() {
  const { token } = useParams<{ token: string }>()
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    if (!token) {
      setState({ status: 'expired' })
      return
    }
    let alive = true

    const load = async () => {
      try {
        const res = await fetch(`/api/public/tracking/${encodeURIComponent(token)}`)
        if (!alive) return
        if (res.status === 401) return setState({ status: 'expired' })
        if (res.status === 404) return setState({ status: 'missing' })
        if (!res.ok) return setState({ status: 'error' })
        setState({ status: 'ok', snapshot: (await res.json()) as PublicSnapshot })
      } catch {
        if (alive) setState({ status: 'error' })
      }
    }

    void load()
    const timer = setInterval(() => void load(), REFRESH_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [token])

  if (state.status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/30">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (state.status !== 'ok') {
    const message =
      state.status === 'expired'
        ? 'Este link expirou. Peça um novo link à central.'
        : state.status === 'missing'
          ? 'Ainda não há posição do entregador para mostrar.'
          : 'Não foi possível carregar o rastreio agora.'
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/30 p-6">
        <div className="max-w-sm text-center">
          <ShieldAlert className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">{message}</p>
        </div>
      </div>
    )
  }

  const { snapshot } = state
  const points: DriverMapPoint[] = [
    {
      driver_id: snapshot.driver_id,
      latitude: snapshot.latitude,
      longitude: snapshot.longitude,
      timestamp: snapshot.updated_at ?? new Date().toISOString(),
      is_stale: false,
    },
  ]

  return (
    <div className="min-h-screen bg-muted/30 p-4">
      <header className="mb-3 flex items-center gap-2">
        <MapPin className="h-5 w-5 text-primary" />
        <h1 className="text-base font-semibold">Acompanhamento da entrega</h1>
      </header>
      <DriverMap points={points} className="h-[70vh]" />
      <p className="mt-2 text-xs text-muted-foreground">
        Posição atualizada automaticamente. Por privacidade, nenhum dado pessoal do entregador é
        exibido.
      </p>
    </div>
  )
}
