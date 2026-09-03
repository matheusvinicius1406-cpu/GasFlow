import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Client, Product, Order, OrderDetail, OrderCreateInput, Customer360, PaginatedResponse, InventoryItem, StockMovement, Delivery, DeliveryDriverExtended, FinancePayment, Receivable, FinanceExpense, CashMovement } from '@/types'

// ── Dashboard Hook ───────────────────────────────────────

export interface DashboardData {
  summary: {
    total_orders: number
    pending_orders: number
    confirmed_orders: number
    delivering_orders: number
    delivered_orders: number
    today_orders: number
    total_revenue: number
    today_revenue: number
    avg_ticket: number
  }
  clients: { total: number }
  products: { total: number }
  drivers: { total: number }
  financial: {
    total_received: number
    today_received: number
    total_pending: number
    total_expenses: number
    today_expenses: number
    cash_balance: number
    result: number
  }
  inventory: {
    total_items: number
    low_stock_count: number
    out_of_stock_count: number
    low_stock_products: Array<{ product_codigo: string; quantity: number; minimum: number }>
  }
  trends: {
    today_orders: { value: number; positive: boolean }
    today_revenue: { value: number; positive: boolean }
    delivering: { value: number; positive: boolean }
    today_received: { value: number; positive: boolean }
  }
  hourly_orders: Array<{ hour: number; count: number }>
  active_deliveries: Array<{
    order_codigo: string
    client_codigo: string
    total: number
    driver_codigo: string | null
    driver_name: string | null
    driver_phone: string | null
    updated_at: string | null
  }>
  recent_orders: Array<{
    codigo: string
    client_codigo: string
    total: number
    status: string
    payment_status: string
    created_at: string | null
  }>
  alerts: Array<{
    type: 'warning' | 'danger' | 'info'
    title: string
    description: string
    action: string
  }>
  generated_at: string
}

export function useDashboard() {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const { data } = await api.dashboard()
      return data as DashboardData
    },
    refetchInterval: 30000, // Refresh every 30s
  })
}

// ── Customer Hooks ───────────────────────────────────────

export interface CustomerSearchParams {
  q?: string
  tipo?: string
  ativo?: boolean
  page?: number
  page_size?: number
}

export function useCustomers(params?: CustomerSearchParams) {
  return useQuery({
    queryKey: ['customers', params],
    queryFn: async () => {
      const { data } = await api.clients.list(params)
      return data as PaginatedResponse<Client>
    },
  })
}

export function useCustomersLegacy() {
  return useQuery({
    queryKey: ['customers', 'legacy'],
    queryFn: async () => {
      const { data } = await api.clients.listLegacy()
      return data as Client[]
    },
  })
}

export function useCustomer(codigo: string) {
  return useQuery({
    queryKey: ['customers', codigo],
    queryFn: async () => {
      const { data } = await api.clients.get(codigo)
      return data as Client
    },
    enabled: !!codigo,
  })
}

export function useCustomer360(codigo: string) {
  return useQuery({
    queryKey: ['customers', codigo, '360'],
    queryFn: async () => {
      const { data } = await api.clients.get360(codigo)
      return data as Customer360
    },
    enabled: !!codigo,
  })
}

export function useCustomerOrders(codigo: string) {
  return useQuery({
    queryKey: ['customers', codigo, 'orders'],
    queryFn: async () => {
      const { data } = await api.clients.getOrders(codigo)
      return data as Order[]
    },
    enabled: !!codigo,
  })
}

export function useCreateCustomer() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: Omit<Client, 'codigo' | 'ativo' | 'created_at' | 'updated_at'>) => {
      const { data: created } = await api.clients.create(data)
      return created as Client
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
    },
  })
}

export function useUpdateCustomer() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, data }: { codigo: string; data: Partial<Client> }) => {
      const { data: updated } = await api.clients.update(codigo, data)
      return updated as Client
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      queryClient.invalidateQueries({ queryKey: ['customers', variables.codigo] })
    },
  })
}

export function useDisableCustomer() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (codigo: string) => {
      const { data } = await api.clients.disable(codigo)
      return data as Client
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
    },
  })
}

// ── Product Hooks ────────────────────────────────────────

export function useProducts() {
  return useQuery({
    queryKey: ['products'],
    queryFn: async () => {
      const { data } = await api.products.list()
      return data as Product[]
    },
  })
}

export function useProduct(codigo: string) {
  return useQuery({
    queryKey: ['products', codigo],
    queryFn: async () => {
      const { data } = await api.products.get(codigo)
      return data as Product
    },
    enabled: !!codigo,
  })
}

export function useCreateProduct() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: Omit<Product, 'codigo' | 'ativo' | 'created_at' | 'updated_at'>) => {
      const { data: created } = await api.products.create(data)
      return created as Product
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
  })
}

export function useUpdateProduct() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, data }: { codigo: string; data: Partial<Product> }) => {
      const { data: updated } = await api.products.update(codigo, data)
      return updated as Product
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      queryClient.invalidateQueries({ queryKey: ['products', variables.codigo] })
    },
  })
}

export function useDisableProduct() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (codigo: string) => {
      const { data } = await api.products.disable(codigo)
      return data as Product
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
  })
}

// ── Order Hooks ──────────────────────────────────────────

export function useOrders(status?: string) {
  return useQuery({
    queryKey: ['orders', status],
    queryFn: async () => {
      const { data } = await api.orders.list(status)
      return data as Order[]
    },
  })
}

export function useOrder(codigo: string) {
  return useQuery({
    queryKey: ['orders', codigo],
    queryFn: async () => {
      const { data } = await api.orders.get(codigo)
      return data as OrderDetail
    },
    enabled: !!codigo,
  })
}

export function useCreateOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: OrderCreateInput) => {
      const { data: created } = await api.orders.create(data)
      return created as Order
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useUpdateOrderStatus() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, status }: { codigo: string; status: string }) => {
      const { data: updated } = await api.orders.updateStatus(codigo, status)
      return updated as Order
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['orders', variables.codigo] })
    },
  })
}

export function useAssignDriver() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, driverCodigo }: { codigo: string; driverCodigo: string }) => {
      const { data: updated } = await api.orders.assignDriver(codigo, driverCodigo)
      return updated as Order
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['orders', variables.codigo] })
    },
  })
}

// ── Inventory Hooks — FASE 7 ───────────────────────────

export interface InventorySearchParams {
  stock_status?: string
  product_type?: string
}

export function useInventoryList(params?: InventorySearchParams) {
  return useQuery({
    queryKey: ['inventory', params],
    queryFn: async () => {
      const { data } = await api.inventory.list(params)
      return data as { items: InventoryItem[]; total: number }
    },
  })
}

export function useInventoryItem(codigo: string) {
  return useQuery({
    queryKey: ['inventory', codigo],
    queryFn: async () => {
      const { data } = await api.inventory.get(codigo)
      return data as InventoryItem
    },
    enabled: !!codigo,
  })
}

export function useInventoryMovements(codigo: string, page = 1) {
  return useQuery({
    queryKey: ['inventory', codigo, 'movements', page],
    queryFn: async () => {
      const { data } = await api.inventory.getMovements(codigo, { page, page_size: 20 })
      return data as { items: StockMovement[]; total: number; page: number; page_size: number; total_pages: number }
    },
    enabled: !!codigo,
  })
}

export function useAddStock() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, quantity, reason }: { codigo: string; quantity: number; reason?: string }) => {
      const { data } = await api.inventory.addStock(codigo, { quantity, reason: reason ?? 'Entrada de estoque' })
      return data
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
      queryClient.invalidateQueries({ queryKey: ['inventory', variables.codigo] })
    },
  })
}

export function useAdjustStock() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, new_quantity, reason }: { codigo: string; new_quantity: number; reason?: string }) => {
      const { data } = await api.inventory.adjust(codigo, { new_quantity, reason: reason ?? 'Ajuste de inventário' })
      return data
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
      queryClient.invalidateQueries({ queryKey: ['inventory', variables.codigo] })
    },
  })
}

export function useRecordLoss() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, quantity, reason }: { codigo: string; quantity: number; reason: string }) => {
      const { data } = await api.inventory.recordLoss(codigo, { quantity, reason })
      return data
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
      queryClient.invalidateQueries({ queryKey: ['inventory', variables.codigo] })
    },
  })
}

export function useSetMinimum() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, minimum_quantity }: { codigo: string; minimum_quantity: number }) => {
      const { data } = await api.inventory.setMinimum(codigo, { minimum_quantity })
      return data as InventoryItem
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
      queryClient.invalidateQueries({ queryKey: ['inventory', variables.codigo] })
    },
  })
}

// ── Delivery Hooks — Bloco A ───────────────────────────

export function useDeliveries(params?: { status?: string; driver_id?: string }) {
  return useQuery({
    queryKey: ['deliveries', params],
    queryFn: async () => {
      const { data } = await api.deliveryOps.listDeliveries(params)
      return data as { deliveries: Delivery[]; count: number }
    },
  })
}

export function useDeliveryDrivers(params?: { status?: string }) {
  return useQuery({
    queryKey: ['delivery-drivers', params],
    queryFn: async () => {
      const { data } = await api.deliveryOps.listDrivers(params)
      return data as { drivers: DeliveryDriverExtended[]; count: number }
    },
  })
}

export function useDeliverySummary() {
  return useQuery({
    queryKey: ['delivery-summary'],
    queryFn: async () => {
      const { data } = await api.deliveryOps.dispatchSummary()
      return data as { deliveries: { total: number; by_status: Record<string, number> }; drivers: { total: number; available: number } }
    },
  })
}

export function useCreateDelivery() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: {
      order_id: string;
      customer_codigo: string;
      customer_name: string;
      address?: { street: string; number: string; complement?: string; neighborhood: string; city?: string; state?: string; zip_code?: string; reference?: string };
      scheduled_at?: string;
      notes?: string;
    }) => {
      const { data: result } = await api.deliveryOps.createDelivery(data)
      return result as { success: boolean; delivery: Delivery }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deliveries'] })
      queryClient.invalidateQueries({ queryKey: ['delivery-summary'] })
    },
  })
}

export function useAssignDelivery() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, driver_id, vehicle_id }: { id: string; driver_id: string; vehicle_id?: string }) => {
      const { data: result } = await api.deliveryOps.assignDelivery(id, { driver_id, vehicle_id })
      return result as { success: boolean; delivery: Delivery }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deliveries'] })
      queryClient.invalidateQueries({ queryKey: ['delivery-summary'] })
      queryClient.invalidateQueries({ queryKey: ['delivery-drivers'] })
    },
  })
}

export function useUpdateDeliveryStatus() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, status, failure_reason, failure_notes, proof_type }: {
      id: string;
      status: string;
      failure_reason?: string;
      failure_notes?: string;
      proof_type?: string;
    }) => {
      const { data: result } = await api.deliveryOps.updateStatus(id, { status, failure_reason, failure_notes, proof_type })
      return result as { success: boolean; delivery: Delivery }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deliveries'] })
      queryClient.invalidateQueries({ queryKey: ['delivery-summary'] })
    },
  })
}

// ── Finance Hooks — Bloco A ────────────────────────────

export function useFinancePayments(params?: { status?: string; order_codigo?: string; page?: number; page_size?: number }) {
  return useQuery({
    queryKey: ['finance-payments', params],
    queryFn: async () => {
      const { data } = await api.finance.listPayments(params)
      return data as PaginatedResponse<FinancePayment>
    },
  })
}

export function useOrderPayments(orderCodigo: string) {
  return useQuery({
    queryKey: ['finance-payments', 'order', orderCodigo],
    queryFn: async () => {
      const { data } = await api.finance.listPayments({ order_codigo: orderCodigo })
      return data as PaginatedResponse<FinancePayment>
    },
    enabled: !!orderCodigo,
  })
}

export function useRegisterPayment() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ order_codigo, amount, method, reference, idempotency_key, notes }: {
      order_codigo: string;
      amount: number;
      method: string;
      reference?: string;
      idempotency_key: string;
      notes?: string;
    }) => {
      const { data } = await api.finance.registerPayment(order_codigo, {
        amount,
        method,
        reference,
        idempotency_key,
        notes,
      })
      return data as { status: string; payment: FinancePayment }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['finance-payments'] })
      queryClient.invalidateQueries({ queryKey: ['finance-receivables'] })
      queryClient.invalidateQueries({ queryKey: ['finance-cash'] })
      queryClient.invalidateQueries({ queryKey: ['finance-balance'] })
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useReceivables(params?: { status?: string; order_codigo?: string; page?: number; page_size?: number }) {
  return useQuery({
    queryKey: ['finance-receivables', params],
    queryFn: async () => {
      const { data } = await api.finance.listReceivables(params)
      return data as PaginatedResponse<Receivable>
    },
  })
}

export function useFinanceExpenses(params?: { status?: string; page?: number; page_size?: number }) {
  return useQuery({
    queryKey: ['finance-expenses', params],
    queryFn: async () => {
      const { data } = await api.finance.listExpenses(params)
      return data as PaginatedResponse<FinanceExpense>
    },
  })
}

export function useCreateExpense() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: { description: string; amount: number; category?: string; date?: string; payment_method?: string; notes?: string }) => {
      const { data: result } = await api.finance.createExpense(data)
      return result as { status: string; expense: FinanceExpense }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['finance-expenses'] })
      queryClient.invalidateQueries({ queryKey: ['finance-cash'] })
      queryClient.invalidateQueries({ queryKey: ['finance-balance'] })
    },
  })
}

export function useCashMovements(params?: { type_filter?: string; page?: number; page_size?: number }) {
  return useQuery({
    queryKey: ['finance-cash', params],
    queryFn: async () => {
      const { data } = await api.finance.listCash(params)
      return data as PaginatedResponse<CashMovement>
    },
  })
}

export function useCashBalance() {
  return useQuery({
    queryKey: ['finance-balance'],
    queryFn: async () => {
      const { data } = await api.finance.cashBalance()
      return data as { balance: number }
    },
  })
}
