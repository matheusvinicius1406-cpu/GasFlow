import { LineChart, TrendingDown, TrendingUp, BarChart3 } from 'lucide-react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Alert } from '@/components/ui/Alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { formatCurrency } from '@/lib/utils'
import { chartVar } from '../chartTokens'
import { toCsvDate } from '../exportPeriodCsv'
import type { PeriodData } from '../useVisaoGeralData'
import { money } from '../useVisaoGeralData'
import { KpiCard } from './KpiCard'

const HORIZONTE = 15
const JANELA_MM = 7

interface Ponto {
  date: string
  real: number | null
  mm7: number | null
  previsao: number | null
}

/** Soma `n` dias a uma data `YYYY-MM-DD`. */
function addDias(date: string, n: number): string {
  const d = new Date(`${date.slice(0, 10)}T00:00:00`)
  d.setDate(d.getDate() + n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate()
  ).padStart(2, '0')}`
}

interface Tendencia {
  pontos: Ponto[]
  inclinacao: number
  projecaoTotal: number
  mediaDiaria: number
}

/**
 * Média móvel de 7 dias + regressão linear simples sobre os recebimentos
 * diários, projetando `HORIZONTE` dias. Cálculo puro no cliente.
 */
function calcularTendencia(period: PeriodData): Tendencia {
  const dias = period.daily
  const n = dias.length
  const valores = dias.map((d) => money(d.receipts))

  const inclinacao = (() => {
    if (n < 2) return 0
    const somaX = (n * (n - 1)) / 2
    const somaY = valores.reduce((s, v) => s + v, 0)
    const somaXY = valores.reduce((s, v, i) => s + i * v, 0)
    const somaX2 = (n * (n - 1) * (2 * n - 1)) / 6
    const denom = n * somaX2 - somaX * somaX
    return denom === 0 ? 0 : (n * somaXY - somaX * somaY) / denom
  })()

  const intercepto = n > 0 ? (valores.reduce((s, v) => s + v, 0) - inclinacao * ((n * (n - 1)) / 2)) / n : 0

  const pontos: Ponto[] = dias.map((d, i) => {
    const janela = valores.slice(Math.max(0, i - JANELA_MM + 1), i + 1)
    const mm7 = i >= JANELA_MM - 1 ? janela.reduce((s, v) => s + v, 0) / JANELA_MM : null
    return {
      date: d.date,
      real: valores[i] ?? 0,
      mm7,
      // Último ponto real recebe o valor da projeção para a linha tracejada conectar.
      previsao: i === n - 1 ? (valores[i] ?? 0) : null,
    }
  })

  const ultimaData = dias[n - 1]?.date ?? ''
  let projecaoTotal = 0
  for (let i = 1; i <= HORIZONTE; i += 1) {
    const projetado = Math.max(0, intercepto + inclinacao * (n - 1 + i))
    projecaoTotal += projetado
    if (ultimaData) pontos.push({ date: addDias(ultimaData, i), real: null, mm7: null, previsao: projetado })
  }

  const mediaDiaria = n > 0 ? valores.reduce((s, v) => s + v, 0) / n : 0
  return { pontos, inclinacao, projecaoTotal, mediaDiaria }
}

/**
 * Tendência (P7) — média móvel 7d e regressão linear sobre o fluxo diário,
 * com projeção de 15 dias. Rótulo honesto: cálculo no cliente, não altera
 * dados.
 */
export function TendenciaSection({ data }: { data: PeriodData }) {
  const { pontos, inclinacao, projecaoTotal, mediaDiaria } = calcularTendencia(data)
  const subindo = inclinacao >= 0

  return (
    <div className="space-y-6" data-testid="tendencia-section">
      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard
          testId="tendencia-inclinacao"
          title="Tendência por dia"
          value={`${subindo ? '+' : '−'}${formatCurrency(Math.abs(inclinacao))}`}
          icon={subindo ? TrendingUp : TrendingDown}
          emphasis={subindo ? 'positive' : 'negative'}
        />
        <KpiCard
          testId="tendencia-projecao"
          title={`Projeção ${HORIZONTE} dias`}
          value={formatCurrency(projecaoTotal)}
          icon={LineChart}
        />
        <KpiCard
          testId="tendencia-media"
          title="Média diária"
          value={formatCurrency(mediaDiaria)}
          icon={BarChart3}
        />
      </div>

      <Alert variant="info" title="Cálculo no cliente">
        Média móvel de {JANELA_MM} dias e regressão linear sobre os recebimentos do período. É uma
        projeção estatística simples — não altera dados.
      </Alert>

      <Card data-testid="tendencia-serie">
        <CardHeader>
          <CardTitle className="text-base">Recebimentos, média móvel e projeção</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <RechartsLineChart data={pontos} margin={{ top: 5, right: 12, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                tickFormatter={(d: string) => toCsvDate(d).slice(0, 5)}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value) => formatCurrency(Number(value))}
                labelFormatter={(label) => toCsvDate(String(label))}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="real"
                name="Recebimentos"
                stroke={chartVar('--success')}
                strokeWidth={2}
                dot={false}
                connectNulls={false}
              />
              <Line
                type="monotone"
                dataKey="mm7"
                name={`Média ${JANELA_MM}d`}
                stroke={chartVar('--info')}
                strokeWidth={2}
                dot={false}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="previsao"
                name={`Projeção ${HORIZONTE}d`}
                stroke={chartVar('--warning')}
                strokeDasharray="5 5"
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            </RechartsLineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  )
}
