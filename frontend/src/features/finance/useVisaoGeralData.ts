import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiClient } from '@/lib/api/client'
import { useToast } from '@/components/ui/Toast'
import type { CashMovement, FinanceExpense, FinancePayment, Receivable } from '@/types'
import { downloadPeriodCsv, toCsvDate } from './exportPeriodCsv'

/**
 * Dados da seção Visão Geral (P5) — o shell busca e injeta (§2.2):
 * núcleo (período + saldo) em bloco, blocos opcionais em `allSettled`
 * (falha de um não derruba os demais) e a tabela de movimentações com
 * busca/ordenação/paginação no servidor (params P1).
 */

export type VisaoTab = 'payments' | 'receivables' | 'expenses' | 'cash'
export type VisaoRow = FinancePayment | Receivable | FinanceExpense | CashMovement
export type SortDir = 'asc' | 'desc'

export interface PeriodDay {
  date: string
  receipts: number | string
  expenses: number | string
  net_result: number | string
}

export interface PeriodComparison {
  receipts_pct?: number | null
  expenses_pct?: number | null
  net_pct?: number | null
}

export interface PeriodData {
  from: string
  to: string
  days: number
  total_receipts: number | string
  total_expenses: number | string
  net_result: number | string
  daily: PeriodDay[]
  comparison: PeriodComparison
}

export interface CategoryRow {
  category: string
  total: number | string
  pct: number | null
}

export interface CategoriesData {
  total: number | string
  items: CategoryRow[]
}

export interface ReceivablesSummaryData {
  open_count: number
  open_total: number | string
  overdue_count: number
  overdue_total: number | string
}

export interface BudgetData {
  year: number
  month: number
  items: { category: string; amount: number | string }[]
  total: number | string
}

export interface ListResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/** Endpoint de lista por aba (todos com q/date_from/date_to/order_by/order — P1). */
const TABLE_ENDPOINT: Record<VisaoTab, string> = {
  payments: '/finance/payments',
  receivables: '/finance/receivables',
  expenses: '/finance/expenses',
  cash: '/finance/cash',
}

/** Whitelist de ordenação por aba (o backend ignora chave fora da lista). */
const SORTABLE: Record<VisaoTab, string[]> = {
  payments: ['created_at', 'paid_at', 'amount', 'order_codigo', 'status', 'method'],
  receivables: ['due_date', 'created_at', 'original_amount', 'paid_amount', 'status', 'customer_codigo'],
  expenses: ['date', 'created_at', 'amount', 'category', 'description'],
  cash: ['created_at', 'amount', 'type', 'balance_after'],
}

const DEFAULT_SORT: Record<VisaoTab, { order_by: string; order: SortDir }> = {
  payments: { order_by: 'created_at', order: 'desc' },
  receivables: { order_by: 'due_date', order: 'asc' },
  expenses: { order_by: 'date', order: 'desc' },
  cash: { order_by: 'created_at', order: 'desc' },
}

const PAGE_SIZE = 20

export function money(value: number | string | null | undefined): number {
  const n = Number(value ?? 0)
  return Number.isFinite(n) ? n : 0
}

/** YYYY-MM-DD local (sem deriva de fuso do toISOString). */
function isoDay(offset: number): string {
  const d = new Date()
  d.setDate(d.getDate() - offset)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function apiMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return 'Nada foi alterado. Tente novamente.'
}

/**
 * Mensagem específica por status no padrão da FinancePage. Devolve `true`
 * quando a lista precisa ser recarregada (404 = o item já não existe).
 */
function reportCancelError(
  toastError: (title: string, description?: string) => void,
  err: unknown,
  what: string
): boolean {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 404) {
    toastError(`${what} não encontrado`, 'Pode já ter sido cancelado — a lista foi recarregada.')
    return true
  }
  if (status === 409) {
    toastError(`${what} não pode ser cancelado`, 'Há uma regra de negócio impedindo — nada foi alterado.')
    return false
  }
  if (status === 403) {
    toastError('Sem permissão', `Seu usuário não pode cancelar este ${what.toLowerCase()}.`)
    return false
  }
  toastError('Erro ao cancelar', 'Nada foi alterado. Tente novamente.')
  return false
}

export function useVisaoGeralData(days: number) {
  const { success, error: toastError } = useToast()

  const [period, setPeriod] = useState<PeriodData | null>(null)
  const [balance, setBalance] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const [budget, setBudget] = useState<BudgetData | null>(null)
  const [budgetFailed, setBudgetFailed] = useState(false)
  const [categories, setCategories] = useState<CategoriesData | null>(null)
  const [categoriesFailed, setCategoriesFailed] = useState(false)
  const [recSummary, setRecSummary] = useState<ReceivablesSummaryData | null>(null)
  const [recSummaryFailed, setRecSummaryFailed] = useState(false)
  const [todayReceived, setTodayReceived] = useState<number | null>(null)
  const [dashboardFailed, setDashboardFailed] = useState(false)

  const [tab, setTab] = useState<VisaoTab>('payments')
  const [orderBy, setOrderBy] = useState<string>(DEFAULT_SORT.payments.order_by)
  const [order, setOrder] = useState<SortDir>(DEFAULT_SORT.payments.order)
  const [page, setPage] = useState(1)
  const [qInput, setQInput] = useState('')
  const [qApplied, setQApplied] = useState('')
  const [tableItems, setTableItems] = useState<VisaoRow[]>([])
  const [tableTotal, setTableTotal] = useState(0)
  const [tableTotalPages, setTableTotalPages] = useState(1)
  const [tableLoading, setTableLoading] = useState(true)
  const [tableError, setTableError] = useState(false)
  const [pending, setPending] = useState<string | null>(null)

  // Guarda contra corrida: uma resposta antiga (período/aba anterior) nunca
  // pode sobrescrever a mais nova — só a requisição mais recente aplica estado.
  const coreIdRef = useRef(0)
  const tableIdRef = useRef(0)

  const range = useMemo(() => ({ from: isoDay(days - 1), to: isoDay(0) }), [days])

  const fetchCore = useCallback(async () => {
    const requestId = ++coreIdRef.current
    setLoading(true)
    setError(false)
    try {
      const core = Promise.allSettled([
        apiClient.get<PeriodData>('/finance/reports/period', { params: { days } }),
        apiClient.get<{ balance: number | string }>('/finance/cash/balance'),
      ])
      const side = Promise.allSettled([
        apiClient.get<BudgetData>('/finance/budget'),
        apiClient.get<CategoriesData>('/finance/reports/categories', { params: { days } }),
        apiClient.get<ReceivablesSummaryData>('/finance/receivables/summary'),
        apiClient.get<{ financial?: { today_received?: number | string } }>('/dashboard'),
      ])
      const [coreResults, sideResults] = await Promise.all([core, side])
      if (requestId !== coreIdRef.current) return

      const [periodRes, balanceRes] = coreResults
      if (periodRes.status === 'fulfilled') setPeriod(periodRes.value.data)
      else setError(true)
      if (balanceRes.status === 'fulfilled') setBalance(money(balanceRes.value.data.balance))

      const [budgetRes, catsRes, recRes, dashRes] = sideResults
      if (budgetRes.status === 'fulfilled') {
        setBudget(budgetRes.value.data)
        setBudgetFailed(false)
      } else {
        setBudgetFailed(true)
      }
      if (catsRes.status === 'fulfilled') {
        setCategories(catsRes.value.data)
        setCategoriesFailed(false)
      } else {
        setCategoriesFailed(true)
      }
      if (recRes.status === 'fulfilled') {
        setRecSummary(recRes.value.data)
        setRecSummaryFailed(false)
      } else {
        setRecSummaryFailed(true)
      }
      if (dashRes.status === 'fulfilled') {
        const today = dashRes.value.data?.financial?.today_received
        setTodayReceived(today === undefined || today === null ? null : money(today))
        setDashboardFailed(false)
      } else {
        setDashboardFailed(true)
      }
    } finally {
      if (requestId === coreIdRef.current) setLoading(false)
    }
  }, [days])

  const fetchTable = useCallback(async () => {
    const requestId = ++tableIdRef.current
    setTableLoading(true)
    setTableError(false)
    try {
      const res = await apiClient.get<ListResponse<VisaoRow>>(TABLE_ENDPOINT[tab], {
        params: {
          ...(qApplied ? { q: qApplied } : {}),
          date_from: range.from,
          date_to: range.to,
          order_by: orderBy,
          order,
          page,
          page_size: PAGE_SIZE,
        },
      })
      if (requestId !== tableIdRef.current) return
      setTableItems(res.data.items ?? [])
      setTableTotal(res.data.total ?? 0)
      setTableTotalPages(res.data.total_pages ?? 1)
    } catch {
      if (requestId !== tableIdRef.current) return
      setTableError(true)
    } finally {
      if (requestId === tableIdRef.current) setTableLoading(false)
    }
  }, [tab, qApplied, orderBy, order, page, range])

  useEffect(() => {
    void fetchCore()
  }, [fetchCore])

  useEffect(() => {
    void fetchTable()
  }, [fetchTable])

  // Debounce da busca: digitação inteira vira um GET só, na página 1.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(1)
      setQApplied(qInput.trim())
    }, 300)
    return () => window.clearTimeout(timer)
  }, [qInput])

  const refresh = useCallback(async () => {
    await Promise.all([fetchCore(), fetchTable()])
  }, [fetchCore, fetchTable])

  const selectTab = useCallback(
    (next: VisaoTab) => {
      if (next === tab) return
      // Invalida o fetch em voo da aba anterior (a resposta antiga não pode
      // re-aparecer) e zera as linhas: os tipos de item mudam por aba.
      tableIdRef.current += 1
      setTab(next)
      setPage(1)
      setOrderBy(DEFAULT_SORT[next].order_by)
      setOrder(DEFAULT_SORT[next].order)
      setTableItems([])
      setTableLoading(true)
    },
    [tab]
  )

  const toggleSort = useCallback(
    (field: string) => {
      if (!SORTABLE[tab].includes(field)) return
      setPage(1)
      if (orderBy === field) {
        setOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'))
      } else {
        setOrderBy(field)
        setOrder('desc')
      }
    },
    [tab, orderBy]
  )

  const createExpense = useCallback(
    async (form: { description: string; amount: number; category: string }): Promise<boolean> => {
      setPending('create-expense')
      try {
        await apiClient.post('/finance/expenses', {
          description: form.description,
          amount: form.amount,
          category: form.category,
        })
        success('Despesa registrada', form.description)
        await refresh()
        return true
      } catch (err) {
        toastError('Erro ao registrar despesa', apiMessage(err))
        return false
      } finally {
        setPending(null)
      }
    },
    [refresh, success, toastError]
  )

  const cancelExpense = useCallback(
    async (expense: FinanceExpense): Promise<boolean> => {
      setPending(`expense-${expense.id}`)
      try {
        await apiClient.post(`/finance/expenses/${expense.id}/cancel`)
        success('Despesa cancelada', expense.description)
        await refresh()
        return true
      } catch (err) {
        if (reportCancelError(toastError, err, 'Despesa')) await refresh()
        return false
      } finally {
        setPending(null)
      }
    },
    [refresh, success, toastError]
  )

  const cancelPayment = useCallback(
    async (payment: FinancePayment): Promise<boolean> => {
      setPending(`payment-${payment.id}`)
      try {
        await apiClient.post(`/payments/${payment.id}/cancel`)
        success('Pagamento cancelado', `Pedido #${payment.order_codigo}`)
        await refresh()
        return true
      } catch (err) {
        if (reportCancelError(toastError, err, 'Pagamento')) await refresh()
        return false
      } finally {
        setPending(null)
      }
    },
    [refresh, success, toastError]
  )

  const registerReceive = useCallback(
    async (orderCodigo: string, form: { amount: number; method: string }): Promise<boolean> => {
      setPending(`receive-${orderCodigo}`)
      try {
        await apiClient.post(`/finance/orders/${orderCodigo}/payments`, {
          amount: form.amount,
          method: form.method,
          idempotency_key: `vg-${orderCodigo}-${Date.now()}`,
        })
        success('Recebimento registrado', `Pedido #${orderCodigo}`)
        await refresh()
        return true
      } catch (err) {
        toastError('Erro ao registrar recebimento', apiMessage(err))
        return false
      } finally {
        setPending(null)
      }
    },
    [refresh, success, toastError]
  )

  const exportCsv = useCallback(() => {
    if (!period) return
    try {
      downloadPeriodCsv(period)
      success('CSV gerado', `Período de ${toCsvDate(period.from)} a ${toCsvDate(period.to)}`)
    } catch {
      toastError('Não foi possível gerar o CSV', 'Tente novamente.')
    }
  }, [period, success, toastError])

  const empty =
    period !== null &&
    period.daily.every((d) => money(d.receipts) === 0 && money(d.expenses) === 0) &&
    tableTotal === 0

  return {
    loading,
    error,
    empty,
    period,
    balance,
    budget,
    budgetFailed,
    categories,
    categoriesFailed,
    recSummary,
    recSummaryFailed,
    todayReceived,
    dashboardFailed,
    pending,
    table: {
      tab,
      items: tableItems,
      total: tableTotal,
      page,
      totalPages: tableTotalPages,
      q: qInput,
      orderBy,
      order,
      loading: tableLoading,
      error: tableError,
    },
    actions: {
      reload: refresh,
      selectTab,
      setQ: setQInput,
      setPage,
      toggleSort,
      createExpense,
      cancelExpense,
      cancelPayment,
      registerReceive,
      exportCsv,
    },
  }
}

export type VisaoGeralData = ReturnType<typeof useVisaoGeralData>
