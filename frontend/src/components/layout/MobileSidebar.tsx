import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { BrandMark } from '@/components/brand/BrandLogo'
import { NavTree } from './nav'

interface MobileSidebarProps {
  isOpen: boolean
  onClose: () => void
}

/**
 * Sidebar mobile — mesma árvore de 7 grupos do desktop (reorg F2 + v2).
 *
 * Renderiza como dialog (`role="dialog" aria-modal`) em telas < md:
 * - Fecha com Escape, clique no backdrop ou navegação;
 * - Trava o scroll do body enquanto aberto;
 * - Foco vai ao drawer ao abrir (e volta ao gatilho via Header on close —
 *   o botão de menu tem aria-label "Abrir menu");
 * - Esconde via `hidden` até o breakpoint md, então um resize para desktop
 *   nunca deixa o drawer "aberto invisível" roubando cliques.
 */
export function MobileSidebar({ isOpen, onClose }: MobileSidebarProps) {
  const drawerRef = useRef<HTMLElement>(null)

  // Escape fecha; scroll do body trava enquanto o drawer está aberto.
  useEffect(() => {
    if (!isOpen) return

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)

    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    // Foco inicial no drawer (fecha o loop de tab dentro do dialog na prática).
    drawerRef.current?.focus()

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = prevOverflow
    }
  }, [isOpen, onClose])

  return (
    <div className={`md:hidden ${isOpen ? '' : 'hidden'}`} aria-hidden={!isOpen}>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50"
        onClick={onClose}
      />

      {/* Sidebar */}
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Menu de navegação"
        tabIndex={-1}
        className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-card outline-none"
      >
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-border px-6">
          <BrandMark />
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Fechar menu">
            <X className="h-5 w-5" />
          </Button>
        </div>

        <nav className="flex-1 overflow-y-auto">
          <NavTree onNavigate={onClose} />
        </nav>
      </aside>
    </div>
  )
}
