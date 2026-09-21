import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { BOOT_SPLASH_ID, BOOT_SPLASH_FADE_MS, dismissBootSplash } from './splash'

/** Monta o nó como o `index.html` o entrega. */
function mountSplash(): HTMLElement {
  const el = document.createElement('div')
  el.id = BOOT_SPLASH_ID
  el.className = 'gf-boot'
  document.body.appendChild(el)
  return el
}

describe('dismissBootSplash', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('é no-op quando o splash não está na página', () => {
    expect(() => dismissBootSplash()).not.toThrow()
  })

  it('inicia o fade e só remove o nó ao fim da transição', () => {
    const splash = mountSplash()

    dismissBootSplash()
    expect(splash).toHaveClass('gf-boot--leave')
    // Continua no DOM durante o fade (senão a revelação seria um corte seco).
    expect(document.getElementById(BOOT_SPLASH_ID)).not.toBeNull()

    vi.advanceTimersByTime(BOOT_SPLASH_FADE_MS)
    expect(document.getElementById(BOOT_SPLASH_ID)).toBeNull()
  })

  it('é idempotente: chamadas repetidas não reiniciam o fade', () => {
    mountSplash()

    dismissBootSplash()
    expect(vi.getTimerCount()).toBe(1)

    dismissBootSplash()
    expect(vi.getTimerCount()).toBe(1)

    vi.advanceTimersByTime(BOOT_SPLASH_FADE_MS)
    expect(document.getElementById(BOOT_SPLASH_ID)).toBeNull()
  })
})
