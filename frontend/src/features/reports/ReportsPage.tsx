import { useState, useEffect, useCallback } from 'react'
import { BarChart3, DollarSign, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { StatCard } from '@/components/ui/StatCard'
import { apiClient } from '@/lib/api/client'

interface DailySummary {
  date: string
  total_receipts: number
  total_expenses: number
  net_result: number
}

function formatMoney(v: number) {
  return `R$ ${Number(v).toFixed(2).replace('.', ',')}`
}

export function ReportsPage() {
  const [summary, setSummary] = useState<DailySummary | null>(null)
  const [balance, setBalance] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const [summaryRes, balanceRes] = await Promise.allSettled([
        apiClient.get('/finance/reports/daily'),
        apiClient.get('/finance/cash/balance'),
      ])

      if (summaryRes.status === 'fulfilled') setSummary(summaryRes.value.data)
      if (balanceRes.status === 'fulfilled') setBalance(Number(balanceRes.value.data.balance) || 0)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <ErrorState
        message="Não foi possível carregar os relatórios."
        onRetry={fetchData}
      />
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Relatórios</h1>
          <p className="text-muted-foreground">Resumo financeiro do dia</p>
        </div>
        <Button onClick={fetchData} variant="outline">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          title="Saldo em Caixa"
          value={formatMoney(balance)}
          icon={DollarSign}
        />
        {summary && (
          <>
            <StatCard
              title="Recebimentos Hoje"
              value={formatMoney(summary.total_receipts)}
              icon={TrendingUp}
            />
            <StatCard
              title="Despesas Hoje"
              value={formatMoney(summary.total_expenses)}
              icon={TrendingDown}
            />
          </>
        )}
      </div>

      {/* Daily Report */}
      {summary && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              Relatório Diário — {summary.date}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-lg border border-border p-4">
                <p className="text-sm text-muted-foreground">Recebimentos</p>
                <p className="text-2xl font-bold text-green-600">
                  {formatMoney(summary.total_receipts)}
                </p>
              </div>
              <div className="rounded-lg border border-border p-4">
                <p className="text-sm text-muted-foreground">Despesas</p>
                <p className="text-2xl font-bold text-destructive">
                  {formatMoney(summary.total_expenses)}
                </p>
              </div>
              <div className="rounded-lg border border-border p-4">
                <p className="text-sm text-muted-foreground">Resultado Líquido</p>
                <p className={`text-2xl font-bold ${summary.net_result >= 0 ? 'text-green-600' : 'text-destructive'}`}>
                  {formatMoney(summary.net_result)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {!summary && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <BarChart3 className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold">Sem dados para exibir</h3>
            <p className="text-sm text-muted-foreground mt-2">
              Os dados de relatórios aparecerão aqui quando houver movimentações financeiras.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
