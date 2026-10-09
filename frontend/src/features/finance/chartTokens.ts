/**
 * Cores dos gráficos lidas dos tokens do tema em tempo de execução —
 * nenhum hex literal nos componentes (R13). Compartilhado entre a Visão
 * Geral (P5) e as analíticas (P6+).
 */
import { useEffect, useState } from 'react'

const CHART_TOKENS = [
  '--success',
  '--destructive',
  '--info',
  '--warning',
  '--muted-foreground',
  '--primary',
]

export function chartVar(name: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || 'currentColor'
}

export function chartToken(index: number): string {
  const token = CHART_TOKENS[index % CHART_TOKENS.length] ?? '--muted-foreground'
  return chartVar(token)
}

/**
 * Re-render quando o tema (classe do `<html>`) muda.
 *
 * `chartVar` resolve a cor no momento do render e o Recharts grava o valor
 * como atributo do SVG — sem este tick as cores ficariam presas ao tema
 * anterior até a próxima renderização qualquer. Chame no componente que
 * usa `chartVar`/`chartToken` (inclui o desenho das camadas do mapa, que
 * acontece num `useEffect`).
 */
export function useChartThemeTick(): number {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return
    const observer = new MutationObserver(() => setTick((n) => n + 1))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style'] })
    return () => observer.disconnect()
  }, [])
  return tick
}
