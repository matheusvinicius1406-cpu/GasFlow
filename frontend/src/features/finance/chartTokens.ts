/**
 * Cores dos gráficos lidas dos tokens do tema em tempo de execução —
 * nenhum hex literal nos componentes (R13). Compartilhado entre a Visão
 * Geral (P5) e as analíticas (P6+).
 */
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
