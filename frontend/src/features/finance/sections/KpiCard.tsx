import { TrendingDown, TrendingUp } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/Card'
import { cn, formatPercent } from '@/lib/utils'

/**
 * Variação vs. período anterior. `invert` é para despesa: subir despesa é
 * notícia ruim, então a seta fica vermelha.
 */
function Delta({ pct, invert = false }: { pct: number | null | undefined; invert?: boolean }) {
  if (pct === null || pct === undefined) return null
  const up = pct >= 0
  const bom = invert ? !up : up
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 text-xs font-medium',
        bom ? 'text-success' : 'text-destructive'
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {formatPercent(Math.abs(pct))}
      <span className="font-normal text-muted-foreground">vs. período anterior</span>
    </span>
  )
}

interface KpiCardProps {
  title: string
  value: string | number
  icon: typeof TrendingUp
  delta?: number | null
  invertDelta?: boolean
  emphasis?: 'positive' | 'negative'
  testId?: string
}

/** Cartão de KPI padrão das seções do Financeiro (token de cor, sem hex). */
export function KpiCard({
  title,
  value,
  icon: Icon,
  delta,
  invertDelta,
  emphasis,
  testId,
}: KpiCardProps) {
  return (
    <Card data-testid={testId}>
      <CardContent className="space-y-2 p-5">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{title}</p>
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
        <p
          className={cn(
            'text-2xl font-bold',
            emphasis === 'positive'
              ? 'text-success'
              : emphasis === 'negative'
                ? 'text-destructive'
                : 'text-foreground'
          )}
        >
          {value}
        </p>
        <Delta pct={delta} invert={invertDelta} />
      </CardContent>
    </Card>
  )
}
