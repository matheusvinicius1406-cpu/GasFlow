import { useCallback, useEffect, useRef, useState } from 'react'
import { Monitor, RefreshCw, X, QrCode, ExternalLink } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'

/**
 * WhatsAppWebPanelPage — moldura React do protótipo híbrido (F1–F3).
 *
 * A VIEW nativa (WebContentsView) é posicionada por bounds sobre o
 * placeholder abaixo — a moldura React fica em volta. O envio de mensagens
 * continua 100% no Baileys; este painel serve APENAS para pairing, status
 * e visibilidade operacional. Sem automação de DOM, sem envio por aqui.
 *
 * Expectativa documentada (não é bug): Baileys (device #1) e a view
 * WhatsApp Web (device #2) são sessões independentes no celular — ambas
 * aparecem em "Dispositivos conectados" e ambas recebem mensagens.
 */

interface WaWebStatus {
  accountId: string
  state: 'closed' | 'loading' | 'connected' | 'qr' | 'disconnected' | 'error'
  lastEventAt: string | null
  lastError: string | null
}

interface WaWebBridge {
  waWebStatuses: () => Promise<{ ok: boolean; enabled: boolean; statuses: WaWebStatus[] }>
  waWebShow: (accountId: string, bounds?: { x: number; y: number; width: number; height: number }) => Promise<unknown>
  waWebBounds: (bounds: { x: number; y: number; width: number; height: number }) => Promise<unknown>
  waWebHide: (accountId: string) => Promise<unknown>
  waWebRePair: (accountId: string) => Promise<unknown>
  waWebClose: (accountId: string) => Promise<unknown>
  onWaWebStatus: (cb: (status: WaWebStatus) => void) => () => void
}

/** Ponte desktop — undefined no navegador puro (página vira informativa). */
function getBridge(): WaWebBridge | undefined {
  return (window as unknown as { gasflow?: Partial<WaWebBridge> }).gasflow as WaWebBridge | undefined
}

const ACCOUNTS = [
  { id: 'primary', label: 'Principal' },
  { id: 'secondary', label: 'Secundária' },
] as const

const STATE_BADGE: Record<WaWebStatus['state'], { variant: 'success' | 'warning' | 'secondary' | 'destructive'; label: string }> = {
  connected: { variant: 'success', label: 'Conectado' },
  qr: { variant: 'warning', label: 'Aguardando QR' },
  loading: { variant: 'warning', label: 'Carregando…' },
  disconnected: { variant: 'secondary', label: 'Desconectado' },
  error: { variant: 'destructive', label: 'Erro' },
  closed: { variant: 'secondary', label: 'Fechado' },
}

/**
 * @param embedded quando true, renderiza sem o cabeçalho próprio — usado como
 * seção "WhatsApp Web" dentro de Contas & Conexão (reorg F3, rota /whatsapp/web removida).
 */
export function WhatsAppWebPanelPage({ embedded = false }: { embedded?: boolean } = {}) {
  const bridge = useRef<WaWebBridge | undefined>(undefined)
  const placeholderRef = useRef<HTMLDivElement | null>(null)
  const [statuses, setStatuses] = useState<Record<string, WaWebStatus>>({})
  const [active, setActive] = useState<string>('primary')
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [hasBridge, setHasBridge] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    bridge.current = getBridge()
    setHasBridge(Boolean(bridge.current?.waWebStatuses))
  }, [])

  const load = useCallback(async () => {
    const b = bridge.current
    if (!b?.waWebStatuses) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(false)
    try {
      const res = await b.waWebStatuses()
      setEnabled(res.enabled)
      setStatuses(Object.fromEntries(res.statuses.map((s) => [s.accountId, s])))
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // F3 — status bridge: push view → main → React (badge reflete em ≤5s).
  useEffect(() => {
    const b = bridge.current
    if (!b?.onWaWebStatus) return
    const off = b.onWaWebStatus((status) => {
      setStatuses((prev) => ({ ...prev, [status.accountId]: status }))
    })
    return off
  }, [hasBridge])

  /** Envia a geometria do placeholder para o main posicionar a view nativa. */
  const syncBounds = useCallback(async (showFor?: string) => {
    const b = bridge.current
    const el = placeholderRef.current
    if (!b || !el) return
    const rect = el.getBoundingClientRect()
    const bounds = {
      x: Math.round(rect.left),
      y: Math.round(rect.top),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    }
    if (bounds.width <= 0 || bounds.height <= 0) return
    if (showFor) await b.waWebShow(showFor, bounds)
    else await b.waWebBounds(bounds)
  }, [])

  // Reposiciona a view nativa quando a moldura muda de tamanho/lugar.
  useEffect(() => {
    const el = placeholderRef.current
    if (!el || !hasBridge) return
    const observer = new ResizeObserver(() => {
      void syncBounds()
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasBridge, syncBounds])

  const openPanel = async () => {
    setBusy(true)
    try {
      await syncBounds(active)
    } finally {
      setBusy(false)
    }
  }

  const rePair = async () => {
    setBusy(true)
    try {
      await bridge.current?.waWebRePair(active)
    } finally {
      setBusy(false)
    }
  }

  const closePanel = async () => {
    setBusy(true)
    try {
      await bridge.current?.waWebClose(active)
    } finally {
      setBusy(false)
    }
  }

  if (!hasBridge) {
    return (
      <div className="space-y-6">
        {!embedded && <Header />}
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Este painel só está disponível no aplicativo desktop do GasFlow.
          </CardContent>
        </Card>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        {!embedded && <Header />}
        <ErrorState message="Não foi possível carregar o painel WhatsApp Web." onRetry={load} />
      </div>
    )
  }

  if (enabled === false) {
    return (
      <div className="space-y-6">
        {!embedded && <Header />}
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            O painel WhatsApp Web está desativado nas configurações do aplicativo.
          </CardContent>
        </Card>
      </div>
    )
  }

  const status = statuses[active] ?? { accountId: active, state: 'closed' as const, lastEventAt: null, lastError: null }
  const badge = STATE_BADGE[status.state] ?? STATE_BADGE.closed

  return (
    <div className="space-y-6">
      {!embedded && <Header />}

      {/* Abas por conta (F2 — partições distintas, contas coexistem) */}
      <div className="flex items-center gap-2" role="tablist" aria-label="Contas WhatsApp">
        {ACCOUNTS.map((acc) => {
          const s = statuses[acc.id]
          const b = STATE_BADGE[s?.state ?? 'closed']
          return (
            <button
              key={acc.id}
              type="button"
              role="tab"
              aria-selected={active === acc.id}
              onClick={() => setActive(acc.id)}
              className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                active === acc.id
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground hover:bg-accent'
              }`}
            >
              {acc.label}
              <span
                aria-label={b?.label}
                className={`h-2 w-2 rounded-full ${
                  s?.state === 'connected'
                    ? 'bg-green-500'
                    : s?.state === 'qr' || s?.state === 'loading'
                      ? 'bg-amber-500'
                      : s?.state === 'error'
                        ? 'bg-red-500'
                        : 'bg-gray-400'
                }`}
              />
            </button>
          )
        })}
      </div>

      {/* Controles */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Monitor className="h-5 w-5" aria-hidden />
            Painel {ACCOUNTS.find((a) => a.id === active)?.label}
            <Badge variant={badge.variant}>{badge.label}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={openPanel} disabled={busy}>
              <ExternalLink className="mr-2 h-4 w-4" aria-hidden />
              Abrir painel
            </Button>
            <Button size="sm" variant="outline" onClick={rePair} disabled={busy}>
              <QrCode className="mr-2 h-4 w-4" aria-hidden />
              Re-parear (QR)
            </Button>
            <Button size="sm" variant="ghost" onClick={closePanel} disabled={busy}>
              <X className="mr-2 h-4 w-4" aria-hidden />
              Fechar
            </Button>
            <Button size="sm" variant="ghost" onClick={load} disabled={busy}>
              <RefreshCw className="mr-2 h-4 w-4" aria-hidden />
              Atualizar status
            </Button>
          </div>
          {status.lastError && (
            <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{status.lastError}</p>
          )}

          {/* Placeholder: a view nativa é renderizada exatamente sobre esta área */}
          <div
            ref={placeholderRef}
            data-testid="wa-web-placeholder"
            className="flex min-h-[480px] items-center justify-center rounded-lg border border-dashed border-border bg-muted/40"
          >
            <p className="text-sm text-muted-foreground">
              {status.state === 'closed'
                ? 'O WhatsApp Web aparece aqui quando você abrir o painel.'
                : 'Sessão do WhatsApp Web ativa nesta área.'}
            </p>
          </div>

          <p className="text-xs text-muted-foreground">
            Este painel é apenas para pareamento e acompanhamento — o envio de mensagens
            continua pelo serviço interno do GasFlow. Ao usar o painel, a conta entra como um
            dispositivo conectado adicional no seu telefone (esperado).
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

function Header() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-foreground">WhatsApp Web (visão operacional)</h1>
      <p className="text-sm text-muted-foreground">
        Acompanhe o estado real da conta, faça o pareamento por QR e re-pareie quando
        necessário — sem tocar no envio automático.
      </p>
    </div>
  )
}
