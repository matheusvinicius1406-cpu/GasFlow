import type { ReactElement } from 'react'
import { ResponsiveContainer } from 'recharts'
import { cn, formatAxisCurrency, formatCurrency } from '@/lib/utils'
import { toCsvDate } from './exportPeriodCsv'

/**
 * Kit dos gráficos da Central Financeira — o boilerplate do Recharts
 * (margem, grid, ticks, eixo em R$, tooltip monetário) vivia copiado em 8
 * gráficos. Aqui ele é definido uma vez e espalhado como props diretas dos
 * elementos do Recharts: `XAxis`/`YAxis`/`Tooltip`/`CartesianGrid` precisam
 * ser filhos REAIS do gráfico (o Recharts os acha por `displayName`), então
 * o kit exporta props/objetos, não wrappers — o único componente é o
 * `ChartFrame`, que fica FORA do gráfico.
 */

/** Margem padrão — `left: 0` porque o eixo Y agora tem largura própria
 * (a margem negativa antiga cortava os rótulos). */
export const CHART_MARGIN = { top: 5, right: 12, left: 0, bottom: 0 } as const

export const axisTick = { fontSize: 11 } as const

export const gridProps = { strokeDasharray: '3 3', stroke: 'var(--border)' } as const

/** Eixo Y monetário: ticks compactos ("R$ 1,5 mil") e largura folgada. */
export const moneyYAxisProps = {
  width: 64,
  tick: axisTick,
  tickFormatter: (value: unknown) => formatAxisCurrency(Number(value)),
} as const

/** Eixo Y de contagens inteiras (entregas, títulos...). */
export const countYAxisProps = {
  width: 40,
  allowDecimals: false,
  tick: axisTick,
} as const

/** Eixo X de datas `YYYY-MM-DD` → `dd/mm` (mesmo formato do CSV e da tabela). */
export const dateXAxisProps = {
  tick: axisTick,
  tickFormatter: (value: unknown) => toCsvDate(String(value)).slice(0, 5),
} as const

/** Tooltip monetário: valor em R$ cheio e rótulo de data por extenso. */
export const moneyTooltipProps = {
  formatter: (value: unknown) => formatCurrency(Number(value)),
  labelFormatter: (label: unknown) => toCsvDate(String(label)),
} as const

/**
 * Container com acessibilidade: `role="img"` + descrição (leitores de tela
 * anunciam o resumo em vez do SVG mudo) e `avoid-break` para o print não
 * partir o gráfico na página do PDF.
 */
export function ChartFrame({
  label,
  height,
  children,
  className,
}: {
  label: string
  height: number
  children: ReactElement
  className?: string
}) {
  return (
    <div role="img" aria-label={label} className={cn('avoid-break', className)}>
      <ResponsiveContainer width="100%" height={height}>
        {children}
      </ResponsiveContainer>
    </div>
  )
}
