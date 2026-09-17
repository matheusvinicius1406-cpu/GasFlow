import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

/**
 * Prende o foco dentro de um overlay (dialog/drawer/slide-over) enquanto
 * `active`:
 *
 * - **Tab/Shift+Tab** ciclam apenas entre os elementos focáveis do container
 *   (sem vazar para a página atrás);
 * - **Foco inicial** vai ao primeiro elemento focável (ou ao próprio
 *   container, se `focusContainer`);
 * - **Ao desativar**, o foco volta ao elemento que estava ativo antes de
 *   abrir (padrão WAI-ARIA APG);
 * - Container precisa ser focável (`tabIndex={-1}`) para o fallback inicial
 *   e para o ciclo funcionar quando não há elemento focável interno.
 *
 * Não busca capturar foco que o usuário moveu para fora de propósito
 * (ex.: devtools); apenas intercepta Tab e devolve o foco se ele escapar.
 */
export function useFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  active: boolean,
  options: { focusContainer?: boolean } = {},
): void {
  const { focusContainer = false } = options
  const previousFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!active) return
    const container = containerRef.current
    if (!container) return

    previousFocusRef.current = document.activeElement as HTMLElement | null

    // Foco inicial: primeiro focável (ordem de tab) ou o próprio container.
    const focusInitial = () => {
      const focusables = container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      const first = focusables[0]
      if (focusContainer || !first) {
        container.focus()
      } else {
        first.focus()
      }
    }
    const raf = requestAnimationFrame(focusInitial)

    const handleKeydown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      // Exclui elementos efetivamente invisíveis. offsetParent é null sem
      // layout (jsdom) e para position:fixed — por isso o fallback de largura
      // via getClientRects, que o jsdom também não resolve; o check real de
      // visibilidade relevante é `hidden` + display:none inline no próprio el.
      const focusables = Array.from(
        container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => {
        if (el.closest('[hidden]')) return false
        if ((el as HTMLElement).style?.display === 'none') return false
        return true
      })

      if (focusables.length === 0) {
        // Só o container é focável: Tab não pode sair dele.
        e.preventDefault()
        container.focus()
        return
      }

      const first: HTMLElement | undefined = focusables[0]
      const last: HTMLElement | undefined = focusables[focusables.length - 1]
      const current = document.activeElement
      const atContainer = current === container

      // Container focado: Tab vai ao primeiro, Shift+Tab ao último.
      if (atContainer) {
        e.preventDefault()
        if (e.shiftKey) {
          if (last) last.focus()
        } else if (first) {
          first.focus()
        }
        return
      }

      if (e.shiftKey) {
        if (first && current === first) {
          e.preventDefault()
          if (last) last.focus()
        }
      } else if (last && current === last) {
        e.preventDefault()
        if (first) first.focus()
      }
    }

    document.addEventListener('keydown', handleKeydown, true)

    return () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('keydown', handleKeydown, true)
      // Devolve o foco ao gatilho, se ele ainda existir no DOM.
      const previous = previousFocusRef.current
      if (previous && document.contains(previous)) {
        previous.focus()
      }
    }
  }, [active, containerRef, focusContainer])
}
