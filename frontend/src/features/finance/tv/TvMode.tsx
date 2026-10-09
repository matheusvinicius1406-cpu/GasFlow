import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { useTheme } from '@/lib/theme'

/** Intervalo da rotação automática de seção no modo TV (R5). */
export const TV_ROTATE_MS = 15_000

export interface TvModeController {
  /** true enquanto o modo TV está ligado. */
  active: boolean
  toggle: () => void
  /** Container que vai para fullscreen (o shell aplica no wrapper da página). */
  containerRef: RefObject<HTMLDivElement | null>
}

/**
 * Modo TV (P10 / R5) — tela de parede para o operador:
 * - `requestFullscreen()` no container (com feature-detect: jsdom não tem);
 * - rotação de seção a cada 15 s (o timer não reinicia a cada troca);
 * - força o tema escuro e **restaura** a preferência anterior ao sair;
 * - `ESC` sai (e o ESC do próprio fullscreen também desliga o modo).
 *
 * Sem animação: a troca é um corte seco, então `prefers-reduced-motion` não
 * muda nada aqui.
 */
export function useTvMode({
  sections,
  currentSlug,
  onSelectSection,
}: {
  sections: string[]
  currentSlug: string
  onSelectSection: (slug: string) => void
}): TvModeController {
  const { themeMode, setThemeMode } = useTheme()
  const [active, setActive] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  // Refs vivos: a rotação não pode reiniciar o timer a cada mudança de seção.
  const sectionsRef = useRef(sections)
  sectionsRef.current = sections
  const currentSlugRef = useRef(currentSlug)
  currentSlugRef.current = currentSlug
  const onSelectSectionRef = useRef(onSelectSection)
  onSelectSectionRef.current = onSelectSection
  const themeModeRef = useRef(themeMode)
  themeModeRef.current = themeMode

  const toggle = useCallback(() => setActive((prev) => !prev), [])

  // Entrar: fullscreen (feature-detect) + tema escuro + `data-tv` no raiz
  // (CSS escala os rótulos dos gráficos para leitura à distância).
  // Sair: restaura os três.
  useEffect(() => {
    if (!active) return
    const element = containerRef.current
    if (element?.requestFullscreen) {
      const request = element.requestFullscreen()
      if (request && typeof request.catch === 'function') request.catch(() => undefined)
    }
    document.documentElement.dataset.tv = 'true'

    const previousTheme = themeModeRef.current
    setThemeMode('dark')
    return () => {
      delete document.documentElement.dataset.tv
      setThemeMode(previousTheme)
      if (typeof document.exitFullscreen === 'function' && document.fullscreenElement) {
        void document.exitFullscreen().catch(() => undefined)
      }
    }
  }, [active, setThemeMode])

  // Rotação de seção a cada TV_ROTATE_MS.
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => {
      const list = sectionsRef.current
      if (list.length === 0) return
      const index = list.indexOf(currentSlugRef.current)
      const next = list[(index + 1) % list.length]
      if (next && next !== currentSlugRef.current) onSelectSectionRef.current(next)
    }, TV_ROTATE_MS)
    return () => window.clearInterval(timer)
  }, [active])

  // ESC sai do modo TV.
  useEffect(() => {
    if (!active) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setActive(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [active])

  // O ESC do fullscreen (tratado pelo navegador) também desliga o modo TV.
  useEffect(() => {
    if (!active) return
    const onChange = () => {
      if (!document.fullscreenElement) setActive(false)
    }
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [active])

  return { active, toggle, containerRef }
}
