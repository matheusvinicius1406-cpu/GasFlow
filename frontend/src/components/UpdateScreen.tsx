import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, Download, Loader2, Rocket } from 'lucide-react'
import { BrandLogo } from '@/components/brand/BrandLogo'
import { Button } from '@/components/ui/Button'
import { useFocusTrap } from '@/lib/hooks/useFocusTrap'
import { useUpdaterState, type UpdateState } from '@/lib/update/updater'

// ── Peças comuns ───────────────────────────────────────────

/** Barra de progresso com faixa indeterminada enquanto não há percentual. */
function UpdateProgressBar({ progress, label }: { progress: number; label: string }) {
  const percent = Math.max(0, Math.min(100, Math.round(progress)))
  const indeterminate = progress <= 0

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : percent}
      className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted"
    >
      {indeterminate ? (
        <span className="gf-anim-indeterminate absolute inset-y-0 w-1/3 rounded-full bg-primary" />
      ) : (
        <span
          className="block h-full rounded-full bg-primary transition-[width] duration-300 ease-out"
          style={{ width: `${percent}%` }}
        />
      )}
    </div>
  )
}

/**
 * Instala e reinicia. O main fecha o app quando dá certo — por isso só
 * reabilitamos a UI no caminho de erro.
 */
function useInstallUpdate() {
  const [installing, setInstalling] = useState(false)
  const [installError, setInstallError] = useState<string | null>(null)

  const install = useCallback(async () => {
    const api = window.gasflowUpdater
    if (!api) return

    setInstalling(true)
    setInstallError(null)
    const result = await api.install()
    if (!result.ok) {
      setInstalling(false)
      setInstallError(result.error ?? 'Não foi possível reiniciar para instalar.')
    }
  }, [])

  return { install, installing, installError }
}

interface UpdateActionsProps {
  onInstall: () => void
  installing: boolean
  installError: string | null
}

// ── Banner (disponível / baixando / adiado) ────────────────

/**
 * Aviso de progresso que NÃO bloqueia o app: o download roda em segundo plano
 * e o usuário continua trabalhando. Aparece centralizado embaixo, acima do
 * conteúdo e abaixo dos tooltips (`--z-tooltip: 500`).
 */
function UpdateBanner({
  state,
  onInstall,
  installing,
  installError,
}: { state: UpdateState } & UpdateActionsProps) {
  const percent = Math.round(state.progress)
  const isReady = state.status === 'ready'

  const title = isReady
    ? `Versão v${state.version} pronta para instalar`
    : state.status === 'downloading'
      ? `Baixando atualização… ${percent}%`
      : `Nova versão v${state.version} disponível`

  const subtitle = isReady
    ? 'Reinicie quando quiser — a atualização será aplicada na hora.'
    : state.status === 'downloading'
      ? 'Roda em segundo plano: pode continuar trabalhando normalmente.'
      : 'Preparando o download…'

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-[420] flex justify-center px-4">
      <div
        data-testid="update-banner"
        role="status"
        aria-live="polite"
        className="gf-anim-pop-in pointer-events-auto w-full max-w-sm rounded-xl border border-border bg-card p-4 shadow-xl"
      >
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"
          >
            {isReady ? <Rocket className="h-4 w-4" /> : <Download className="h-4 w-4" />}
          </span>

          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground">{title}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>

            {!isReady && (
              <div className="mt-2.5">
                <UpdateProgressBar progress={state.progress} label="Progresso do download da atualização" />
              </div>
            )}

            {isReady && (
              <Button size="sm" className="mt-3 w-full" onClick={onInstall} disabled={installing}>
                {installing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    Reiniciando…
                  </>
                ) : (
                  'Reiniciar e instalar'
                )}
              </Button>
            )}

            {installError && (
              <p role="alert" className="mt-2 text-xs text-destructive">
                {installError}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Overlay (pronto) ───────────────────────────────────────

/**
 * O momento que exige decisão: a versão já foi baixada e aplicar exige
 * reiniciar. É a única parte bloqueante — e "Depois" devolve o usuário ao app,
 * rebaixando o aviso para o banner (nada fica perdido).
 */
function UpdateReadyOverlay({
  state,
  onLater,
  onInstall,
  installing,
  installError,
}: { state: UpdateState; onLater: () => void } & UpdateActionsProps) {
  const cardRef = useRef<HTMLDivElement>(null)
  useFocusTrap(cardRef, true)

  // Escape equivale a "Depois" (WAI-ARIA APG para diálogos).
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onLater()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onLater])

  const failed = !!installError

  return (
    <div className="gf-anim-fade-in fixed inset-0 z-[450] flex items-center justify-center overflow-y-auto bg-background/85 p-4 backdrop-blur-md">
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-ready-title"
        aria-describedby="update-ready-description"
        tabIndex={-1}
        className="gf-anim-pop-in w-full max-w-md rounded-2xl border border-border bg-card p-8 text-center shadow-xl"
      >
        {/* Marca com anel pulsante — indica que o app está vivo, não travado */}
        <div className="relative mx-auto mb-5 grid h-20 w-20 place-items-center">
          <span
            aria-hidden="true"
            className="gf-anim-pulse-ring absolute inset-0 rounded-full border-2 border-primary/40"
          />
          <span
            aria-hidden="true"
            className="gf-anim-complete grid h-16 w-16 place-items-center rounded-full bg-primary/10 text-primary"
          >
            {failed ? <AlertTriangle className="h-7 w-7 text-destructive" /> : <Rocket className="h-7 w-7" />}
          </span>
        </div>

        <h2 id="update-ready-title" className="text-xl font-semibold text-foreground">
          {failed ? 'Não deu para reiniciar' : 'Atualização pronta'}
        </h2>

        <div className="mt-3 flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <BrandLogo size="sm" />
          <span>Nova versão</span>
          <span className="relative overflow-hidden rounded-full border border-border px-2.5 py-0.5">
            <span className="relative z-10 text-xs font-medium text-foreground">v{state.version}</span>
            <span
              aria-hidden="true"
              className="gf-anim-sheen absolute inset-y-0 left-0 w-6 bg-foreground/10 blur-[6px]"
            />
          </span>
        </div>

        <p id="update-ready-description" className="mt-3 text-sm text-muted-foreground">
          {failed
            ? 'A atualização já está baixada e será aplicada quando o GasFlow for fechado. Você pode tentar de novo ou continuar trabalhando.'
            : 'A versão já foi baixada. O GasFlow precisa reiniciar para aplicá-la — seus dados estão salvos e nada se perde no caminho.'}
        </p>

        <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-success">
          <Check className="h-3.5 w-3.5" aria-hidden="true" />
          Download concluído
        </p>

        {installError && (
          <p role="alert" className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {installError}
          </p>
        )}

        <div className="mt-6 flex flex-col gap-2">
          <Button onClick={onInstall} disabled={installing}>
            {installing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Reiniciando…
              </>
            ) : (
              'Reiniciar e instalar agora'
            )}
          </Button>
          <Button variant="ghost" onClick={onLater} disabled={installing}>
            Depois
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Orquestrador ───────────────────────────────────────────

/**
 * Tela de atualização do auto-update (Electron).
 *
 * Reparte os estados da ponte para não sobrepor avisos:
 *
 * - `available` / `downloading` → banner de progresso, não bloqueante;
 * - `ready` → overlay de decisão, dispensável em "Depois" (volta como banner);
 * - `checking` / `error` → `UpdateNotifier` (aviso de canto);
 * - `idle` / `up-to-date` → nada.
 *
 * Fora do Electron (`window.gasflowUpdater` ausente) não renderiza nada.
 */
export function UpdateScreen() {
  const state = useUpdaterState()
  const { install, installing, installError } = useInstallUpdate()

  // Versão cujo overlay o usuário adiou — o aviso vira banner, não desaparece.
  const [snoozedVersion, setSnoozedVersion] = useState<string | null>(null)
  const handleLater = useCallback(() => setSnoozedVersion(state.version), [state.version])

  const actions = { onInstall: install, installing, installError }

  if (state.status === 'ready') {
    if (snoozedVersion !== state.version) {
      return <UpdateReadyOverlay state={state} onLater={handleLater} {...actions} />
    }
    return <UpdateBanner state={state} {...actions} />
  }

  if (state.status === 'available' || state.status === 'downloading') {
    return <UpdateBanner state={state} {...actions} />
  }

  return null
}

export default UpdateScreen
