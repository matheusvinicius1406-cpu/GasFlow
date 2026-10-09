import { CalendarDays, Clock } from 'lucide-react'
import { Alert } from '@/components/ui/Alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'
import { toCsvDate } from '../exportPeriodCsv'
import type { CalendarioData } from '../useAnalyticsData'
import { money } from '../useVisaoGeralData'

const INTENSITY_CLASS = [
  'bg-muted text-muted-foreground',
  'bg-success/20 text-foreground',
  'bg-success/40 text-foreground',
  'bg-success/60 text-foreground',
  'bg-success text-white',
]

function intensidade(valor: number, max: number): number {
  if (valor <= 0 || max <= 0) return 0
  const ratio = valor / max
  if (ratio <= 0.25) return 1
  if (ratio <= 0.5) return 2
  if (ratio <= 0.75) return 3
  return 4
}

/**
 * Calendário (P7) — heatmap do fluxo de recebimentos por dia do período e
 * por hora do dia. As despesas não têm hora no registro, então o mapa por
 * hora cobre só recebimentos (`paid_at`).
 */
export function CalendarioSection({ data }: { data: CalendarioData }) {
  const dias = data.period.daily
  const maxDia = Math.max(0, ...dias.map((d) => money(d.receipts)))
  const maxHora = Math.max(0, ...data.hourly.buckets.map((b) => money(b.total)))

  const porHora = Array.from({ length: 24 }, (_, hour) => {
    const found = data.hourly.buckets.find((b) => b.hour === hour)
    return { hour, count: found?.count ?? 0, total: money(found?.total) }
  })

  return (
    <div className="space-y-6" data-testid="calendario-section">
      <Card data-testid="calendario-dias">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarDays className="h-4 w-4 text-muted-foreground" />
            Recebimentos por dia
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-7 gap-1 sm:grid-cols-10 lg:grid-cols-14">
            {dias.map((d) => {
              const valor = money(d.receipts)
              const nivel = intensidade(valor, maxDia)
              return (
                <div
                  key={d.date}
                  title={`${toCsvDate(d.date)} · ${formatCurrency(valor)}`}
                  className={cn(
                    'flex aspect-square items-center justify-center rounded text-xs font-medium',
                    INTENSITY_CLASS[nivel]
                  )}
                >
                  {toCsvDate(d.date).slice(0, 2)}
                </div>
              )
            })}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Menos</span>
            {INTENSITY_CLASS.map((cls, i) => (
              <span key={i} className={cn('h-3 w-3 rounded-sm', cls)} aria-hidden />
            ))}
            <span>Mais</span>
          </div>
        </CardContent>
      </Card>

      <Alert variant="info" title="Por hora do dia">
        As despesas não têm hora no registro — o mapa por hora considera só os recebimentos
        (horário do pagamento).
      </Alert>

      <Card data-testid="calendario-horas">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Clock className="h-4 w-4 text-muted-foreground" />
            Recebimentos por hora
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* 6 colunas no celular (4 linhas), 12 no tablet e 24 no desktop —
              o grid fixo de 24 colunas virava microscópio no mobile. */}
          <div className="grid grid-cols-6 gap-1 sm:grid-cols-12 lg:[grid-template-columns:repeat(24,minmax(0,1fr))]">
            {porHora.map((h) => (
              <div
                key={h.hour}
                title={`${String(h.hour).padStart(2, '0')}h · ${h.count} recebimento${
                  h.count === 1 ? '' : 's'
                } · ${formatCurrency(h.total)}`}
                className={cn(
                  'flex aspect-square items-center justify-center rounded text-[10px] font-medium',
                  INTENSITY_CLASS[intensidade(h.total, maxHora)]
                )}
              >
                {h.hour}
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Total no período: {formatCurrency(money(data.hourly.total))} em{' '}
            {formatNumber(porHora.reduce((s, h) => s + h.count, 0))} recebimentos.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
