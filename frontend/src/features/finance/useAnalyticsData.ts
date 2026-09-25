import { useCallback, useEffect, useRef, useState } from 'react'
import { apiClient } from '@/lib/api/client'
import { useToast } from '@/components/ui/Toast'
import { apiMessage } from './useVisaoGeralData'

/**
 * Dados das seções de analíticas (P6) — o shell busca e injeta (§2.2 do
 * plano da Fase 2). Cada hook só faz a chamada quando a seção está ativa
 * (`enabled`), então trocar de aba busca um endpoint, não os quatro.
 */

// ── Tipos das respostas (espelham app/presentation/schemas/financial.py) ──

export interface DreExpenseItem {
  category: string
  total: number | string
  pct: number | null
}

export interface DreData {
  from: string
  to: string
  days: number
  revenue: number | string
  cmv: number | string
  gross_profit: number | string
  expenses: number | string
  result: number | string
  /** % da receita com custo conhecido (None quando receita = 0). */
  cmv_coverage: number | null
  expense_items: DreExpenseItem[]
}

export interface ProductMarginItem {
  product_codigo: string
  product_nome: string
  quantity: number
  revenue: number | string
  unit_cost: number | string | null
  /** false quando o produto não tem nota de compra CONFIRMED. */
  cost_known: boolean
  margin: number | string | null
  margin_pct: number | null
}

export interface ProductsData {
  from: string
  to: string
  days: number
  revenue: number | string
  items: ProductMarginItem[]
}

export interface ProjectionDay {
  date: string
  inflow: number | string
  outflow: number | string
  balance: number | string
}

export interface ProjectionData {
  generated_at: string
  horizon: number
  current_balance: number | string
  expected_in: number | string
  avg_daily_expenses: number | string
  expected_out: number | string
  projected_balance: number | string
  daily: ProjectionDay[]
  /** Rótulo honesto do modelo (sem ML) — exibido na seção. */
  model: string
}

export interface CategoryBreakdownItem {
  category: string
  total: number | string
  pct: number | null
}

export interface CategoryBreakdownData {
  from: string
  to: string
  days: number
  total: number | string
  items: CategoryBreakdownItem[]
}

export interface BudgetItemRow {
  category: string
  amount: number | string
}

export interface BudgetMonth {
  year: number
  month: number
  items: BudgetItemRow[]
  total: number | string
}

export interface BudgetSectionData {
  budget: BudgetMonth
  realized: CategoryBreakdownData
}

export interface ReportState<T> {
  data: T | null
  loading: boolean
  error: boolean
  reload: () => Promise<void>
}

/**
 * GET de um relatório com guarda contra corrida (uma resposta antiga nunca
 * sobrescreve a mais recente). `path === null` desliga a busca — usado para
 * só carregar a seção ativa.
 */
function useReport<T>(
  path: string | null,
  params: Record<string, number | string> | null
): ReportState<T> {
  const enabled = path !== null && params !== null
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState(false)

  const requestIdRef = useRef(0)
  const paramsRef = useRef(params)
  paramsRef.current = params
  const paramsKey = params === null ? null : JSON.stringify(params)

  const reload = useCallback(async () => {
    if (path === null || paramsKey === null) return
    const requestId = ++requestIdRef.current
    setLoading(true)
    setError(false)
    try {
      const res = await apiClient.get<T>(path, {
        params: (paramsRef.current ?? undefined) as Record<string, number | string> | undefined,
      })
      if (requestId !== requestIdRef.current) return
      setData(res.data)
    } catch {
      if (requestId !== requestIdRef.current) return
      setError(true)
    } finally {
      if (requestId === requestIdRef.current) setLoading(false)
    }
  }, [path, paramsKey])

  useEffect(() => {
    if (paramsKey === null) {
      requestIdRef.current += 1
      setData(null)
      setError(false)
      setLoading(false)
      return
    }
    void reload()
  }, [paramsKey, reload])

  return { data, loading, error, reload }
}

/** GET /finance/reports/dre — DRE gerencial com CMV ponderado e cobertura. */
export function useDreData(days: number, enabled: boolean): ReportState<DreData> {
  return useReport<DreData>(enabled ? '/finance/reports/dre' : null, enabled ? { days } : null)
}

/** GET /finance/reports/products — margem por produto (`cost_known`). */
export function useProductsData(days: number, enabled: boolean): ReportState<ProductsData> {
  return useReport<ProductsData>(
    enabled ? '/finance/reports/products' : null,
    enabled ? { days } : null
  )
}

/** GET /finance/reports/projection — projeção de caixa (modelo sem ML). */
export function useProjectionData(horizon: number, enabled: boolean): ReportState<ProjectionData> {
  return useReport<ProjectionData>(
    enabled ? '/finance/reports/projection' : null,
    enabled ? { horizon } : null
  )
}

export interface OrcamentoState {
  data: BudgetSectionData | null
  loading: boolean
  error: boolean
  /** true enquanto um PUT do orçamento está em voo. */
  saving: boolean
  reload: () => Promise<void>
  save: (
    year: number,
    month: number,
    items: { category: string; amount: number }[]
  ) => Promise<boolean>
}

/**
 * Orçamento (V4): lê o mês corrente e o realizado por categoria do período
 * (mesmo endpoint do donut da Visão Geral) e permite substituir o mês via
 * PUT replace-all. Escrita gated por `finance.write` no componente.
 */
export function useOrcamentoData(days: number, enabled: boolean): OrcamentoState {
  const { success, error: toastError } = useToast()
  const [data, setData] = useState<BudgetSectionData | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState(false)
  const [saving, setSaving] = useState(false)
  const requestIdRef = useRef(0)

  const reload = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setLoading(true)
    setError(false)
    try {
      const [budgetRes, realizedRes] = await Promise.all([
        apiClient.get<BudgetMonth>('/finance/budget'),
        apiClient.get<CategoryBreakdownData>('/finance/reports/categories', { params: { days } }),
      ])
      if (requestId !== requestIdRef.current) return
      setData({ budget: budgetRes.data, realized: realizedRes.data })
    } catch {
      if (requestId !== requestIdRef.current) return
      setError(true)
    } finally {
      if (requestId === requestIdRef.current) setLoading(false)
    }
  }, [days])

  useEffect(() => {
    if (!enabled) {
      requestIdRef.current += 1
      setData(null)
      setError(false)
      setLoading(false)
      return
    }
    void reload()
  }, [enabled, reload])

  const save = useCallback(
    async (
      year: number,
      month: number,
      items: { category: string; amount: number }[]
    ): Promise<boolean> => {
      setSaving(true)
      try {
        await apiClient.put('/finance/budget', { year, month, items })
        success('Orçamento salvo', `${String(month).padStart(2, '0')}/${year}`)
        await reload()
        return true
      } catch (err) {
        toastError('Erro ao salvar orçamento', apiMessage(err))
        return false
      } finally {
        setSaving(false)
      }
    },
    [reload, success, toastError]
  )

  return { data, loading, error, saving, reload, save }
}
