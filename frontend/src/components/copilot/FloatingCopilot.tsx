import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Sparkles, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useFocusTrap } from '@/lib/hooks/useFocusTrap'
import { CopilotPage } from '@/features/ai/CopilotPage'

const OPEN_KEY = 'gasflow.copilot.open'

/**
 * Bolinha flutuante da IA (reorg F4 — docs/reorg-plan.md §3.2).
 *
 * FAB no canto inferior-direito que abre um painel slide-over com o chat do
 * Copilot. Substitui o item de menu "Inteligência" e a rota /intelligence
 * (deletadas). Some em /login e rotas do motorista.
 *
 * Persistência: aberto/fechado no localStorage.
 */
export function FloatingCopilot() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(OPEN_KEY) === '1'
    } catch {
      return false
    }
  })
  const panelRef = useRef<HTMLDivElement>(null)

  // Focus trap: foco entra no painel, Tab cicla só dentro dele e volta ao
  // FAB ao fechar. Painel é focável (tabIndex=-1) e recebe o foco direto.
  useFocusTrap(panelRef, open, { focusContainer: true })

  // Escape fecha o painel.
  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open])

  // Rotas sem a bolinha: login e console do motorista.
  if (pathname === '/login' || pathname.startsWith('/driver')) return null

  const toggle = (next: boolean) => {
    setOpen(next)
    try {
      if (next) localStorage.setItem(OPEN_KEY, '1')
      else localStorage.removeItem(OPEN_KEY)
    } catch {
      /* storage indisponível — estado só em memória */
    }
  }

  return (
    <>
      {/* FAB — fora do fluxo dos módulos, acima de tudo. Com o painel
          aberto sai do tab order (tabIndex=-1): é puro visual, fechar é
          Escape/X/backdrop. */}
      <button
        type="button"
        aria-label={open ? 'Fechar assistente IA' : 'Abrir assistente IA'}
        aria-expanded={open}
        tabIndex={open ? -1 : 0}
        onClick={() => toggle(!open)}
        className={cn(
          'fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full',
          'bg-primary text-primary-foreground shadow-lg transition-all duration-200',
          'hover:scale-105 hover:shadow-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
          open && 'pointer-events-none scale-0 opacity-0',
        )}
      >
        <Sparkles className="h-6 w-6" />
      </button>

      {/* Slide-over */}
      <div
        ref={panelRef}
        role="dialog"
        aria-label="Assistente IA"
        aria-modal="true"
        tabIndex={-1}
        className={cn(
          'fixed bottom-0 right-0 top-0 z-50 w-[380px] max-w-[100vw]',
          'border-l border-border bg-background/95 shadow-2xl backdrop-blur',
          'transition-transform duration-200 ease-out',
          'outline-none focus-visible:ring-0',
          open ? 'translate-x-0' : 'translate-x-full',
        )}
        aria-hidden={!open}
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <span className="text-sm font-semibold text-foreground">Assistente IA</span>
            <button
              type="button"
              aria-label="Fechar painel"
              onClick={() => toggle(false)}
              className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="min-h-0 flex-1 p-4">
            <CopilotPage embedded />
          </div>
        </div>
      </div>
    </>
  )
}
