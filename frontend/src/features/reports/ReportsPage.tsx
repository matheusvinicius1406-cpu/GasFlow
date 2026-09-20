import { useCallback, useEffect, useState } from 'react'
import {
  Bar,
  CartesianGrid,
  Legend,
  Line,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  ArrowLeftRight,
  BarChart3,
  DollarSign,
  FileDown,
  Loader2,
  Printer,
  RefreshCw,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { useToast } from '@/components/ui/Toast'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'
import { apiClient } from '@/lib/api/client'
import { exportCurrentViewPdf } from '@/lib/exportPdf'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { downloadPeriodCsv, toCsvDate, type PeriodReportCsvInput } from './periodCsv'
import { DeliveryCharts } from './DeliveryCharts'

/**
 * Relatórios — F10.9
 *
 * Antes esta página só sabia responder "o que entrou e saiu HOJE": um par de
 * números, um botão de refresh sem rótulo e nada para comparar ou levar da
 * tela (sem filtro de período, sem exportar, sem imprimir).
 *
 * Agora ela responde a pergunta de verdade do dono: "esse mês está melhor que
 * o anterior em quê?". Daí o filtro de período, a comparação com o período
 * anterior de mesma duração e a série diária — os três vêm de uma chamada só
 * (`/finance/reports/period`).
 */

type Preset = { days: number; label: string }

const PRESETS: Preset[] = [
  { days: 1, label: 'Hoje' },
  { days: 7, label: '7 dias' },
  { days: 30, label: '30 dias' },
  { days: 90, label: '90 dias' },
]

interface PeriodDay {
  date: string
  receipts: string | number
  expenses: string | number
  net_result: string | number
}

interface PeriodReport {
  from: string
  to: string
  days: number
  total_receipts: string | number
  total_expenses: string | number
  net_result: string | number
  daily: PeriodDay[]
  previous: {
    from: string
    to: string
    total_receipts: string | number
    total_expenses: string | number
    net_result: string | number
  }
  comparison: {
    receipts_pct: number | null
    expenses_pct: number | null
    net_pct: number | null
  }
}

function money(value: string | number): number {
  return Number(value) || 0
}

/**
 * Variação do período. `invert` é para despesa: subir despesa é notícia ruim,
 * então a seta fica vermelha — o contrário de recebimento/resultado.
 */
function Delta({ pct, invert = false }: { pct: number | null | undefined; invert?: boolean }) {
  if (pct === null || pct === undefined) {
    return <span className="text-xs text-muted-foreground">sem base de comparação</span>
  }
  const up = pct >= 0
  const bom = invert ? !up : up
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium ${bom ? 'text-success' : 'text-destructive'}`}
    >
      <Icon className="h-3.5 w-3.5" />
      {formatPercent(Math.abs(pct))}
      <span className="font-normal text-muted-foreground">vs período anterior</span>
    </span>
  )
}

function MetricCard({
  title,
  value,
  icon: Icon,
  delta,
  invertDelta,
  emphasis,
  testId,
}: {
  title: string
  value: string
  icon: typeof DollarSign
  delta?: number | null
  invertDelta?: boolean
  emphasis?: 'positive' | 'negative'
  testId: string
}) {
  return (
    <Card data-testid={testId}>
      <CardContent className="space-y-2 p-5">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{title}</p>
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
        <p
          className={`text-2xl font-bold ${
            emphasis === 'positive' ? 'text-success' : emphasis === 'negative' ? 'text-destructive' : 'text-foreground'
          }`}
        >
          {value}
        </p>
        {delta !== undefined && <Delta pct={delta} invert={invertDelta} />}
      </CardContent>
    </Card>
  )
}

export function ReportsPage() {
  const toast = useToast()
  const [days, setDays] = useState(30)
  const [report, setReport] = useState<PeriodReport | null>(null)
  const [balance, setBalance] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [exporting, setExporting] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      // O saldo é de agora (não do período) — falha dele não derruba o resto.
      const [reportRes, balanceRes] = await Promise.allSettled([
        apiClient.get<PeriodReport>('/finance/reports/period', { params: { days } }),
        apiClient.get<{ balance: string | number }>('/finance/cash/balance'),
      ])

      if (reportRes.status === 'rejected') {
        setError(true)
        return
      }
      setReport(reportRes.value.data)
      if (balanceRes.status === 'fulfilled') setBalance(money(balanceRes.value.data.balance))
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  const exportCsv = () => {
    if (!report) return
    try {
      downloadPeriodCsv(report as PeriodReportCsvInput)
      toast.success('CSV gerado', `Período de ${toCsvDate(report.from)} a ${toCsvDate(report.to)}`)
    } catch {
      toast.error('Não foi possível gerar o CSV', 'Tente novamente.')
    }
  }

  const printView = async () => {
    setExporting(true)
    try {
      const mode = await exportCurrentViewPdf()
      if (mode === 'print') {
        toast.info('Abrindo a impressão do sistema', 'Escolha "Salvar como PDF" para guardar o relatório.')
      }
    } catch (e) {
      toast.error('Falha ao gerar o PDF', e instanceof Error ? e.message : 'Erro inesperado.')
    } finally {
      setExporting(false)
    }
  }

  if (loading && !report) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error && !report) {
    return <ErrorState message="Não foi possível carregar os relatórios." onRetry={fetchData} />
  }

  const semMovimento =
    report !== null && report.daily.every((d) => money(d.receipts) === 0 && money(d.expenses) === 0)

  return (
    <Page>
      <PageHeader>
        <PageTitle
          subtitle={
            report
              ? `${toCsvDate(report.from)} a ${toCsvDate(report.to)} · ${report.days} dia${report.days > 1 ? 's' : ''}`
              : 'Financeiro e entregas por período'
          }
        >
          Relatórios
        </PageTitle>
        <PageActions>
          <Button onClick={() => void fetchData()} variant="outline" disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Atualizar
          </Button>
          <Button onClick={exportCsv} variant="outline" disabled={!report}>
            <FileDown className="h-4 w-4" />
            Exportar CSV
          </Button>
          <Button onClick={() => void printView()} disabled={!report || exporting}>
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Printer className="h-4 w-4" />}
            Imprimir
          </Button>
        </PageActions>
      </PageHeader>

      {/* Filtro de período — um grupo só, com o ativo visível */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">Período:</span>
        <div className="flex items-center gap-1" role="group" aria-label="Período do relatório">
          {PRESETS.map((p) => (
            <Button
              key={p.days}
              size="sm"
              variant={days === p.days ? 'default' : 'outline'}
              onClick={() => setDays(p.days)}
            >
              {p.label}
            </Button>
          ))}
        </div>
        {report && report.days > 1 && (
          <Badge variant="secondary" className="ml-1">
            <ArrowLeftRight className="mr-1 h-3 w-3" />
            comparado com {toCsvDate(report.previous.from)} – {toCsvDate(report.previous.to)}
          </Badge>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          testId="metric-balance"
          title="Saldo em Caixa"
          value={formatCurrency(balance)}
          icon={DollarSign}
        />
        <MetricCard
          testId="metric-receipts"
          title="Recebimentos"
          value={formatCurrency(money(report?.total_receipts ?? 0))}
          icon={TrendingUp}
          delta={report?.comparison.receipts_pct}
        />
        <MetricCard
          testId="metric-expenses"
          title="Despesas"
          value={formatCurrency(money(report?.total_expenses ?? 0))}
          icon={TrendingDown}
          delta={report?.comparison.expenses_pct}
          invertDelta
        />
        <MetricCard
          testId="metric-net"
          title="Resultado Líquido"
          value={formatCurrency(money(report?.net_result ?? 0))}
          icon={BarChart3}
          delta={report?.comparison.net_pct}
          emphasis={money(report?.net_result ?? 0) >= 0 ? 'positive' : 'negative'}
        />
      </div>

      {semMovimento && (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={BarChart3}
              title="Sem movimentações neste período"
              description="Nenhum recebimento ou despesa no período escolhido. Troque o filtro ou registre os lançamentos no Financeiro."
            />
          </CardContent>
        </Card>
      )}

      {report && !semMovimento && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Entradas, saídas e resultado por dia</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={report.daily} margin={{ top: 5, right: 12, left: -12, bottom: 0 }}>
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
                <Bar dataKey="receipts" name="Recebimentos" fill="#16a34a" radius={[3, 3, 0, 0]} />
                <Bar dataKey="expenses" name="Despesas" fill="#dc2626" radius={[3, 3, 0, 0]} />
                <Line type="monotone" dataKey="net_result" name="Resultado" stroke="#2563eb" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {report && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Detalhe por dia</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-96 overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Dia</TableHead>
                    <TableHead className="text-right">Recebimentos</TableHead>
                    <TableHead className="text-right">Despesas</TableHead>
                    <TableHead className="text-right">Resultado</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.daily.map((dia) => (
                    <TableRow key={dia.date}>
                      <TableCell className="font-medium">{toCsvDate(dia.date)}</TableCell>
                      <TableCell className="text-right text-success">
                        {formatCurrency(money(dia.receipts))}
                      </TableCell>
                      <TableCell className="text-right text-destructive">
                        {formatCurrency(money(dia.expenses))}
                      </TableCell>
                      <TableCell
                        className={`text-right font-medium ${
                          money(dia.net_result) >= 0 ? 'text-foreground' : 'text-destructive'
                        }`}
                      >
                        {formatCurrency(money(dia.net_result))}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
                <TableFooter>
                  <TableRow>
                    <TableCell className="font-semibold">Total</TableCell>
                    <TableCell className="text-right font-semibold">
                      {formatCurrency(money(report.total_receipts))}
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {formatCurrency(money(report.total_expenses))}
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {formatCurrency(money(report.net_result))}
                    </TableCell>
                  </TableRow>
                </TableFooter>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Entregas: mantém o recorte próprio (7/30/90) com o filtro da tela */}
      <DeliveryCharts />
    </Page>
  )
}
