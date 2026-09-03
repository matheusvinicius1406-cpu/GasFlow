// ── Client (Backend: /clients/) ─────────────────────────
export interface Client {
  codigo: string
  nome: string
  telefone: string
  telefone_secundario?: string
  rua: string
  numero: string
  complemento?: string
  referencia?: string
  bairro: string
  observacoes?: string
  ativo: boolean
  tipo?: string
  email?: string
  created_at: string
  updated_at: string
}

export type ClientType = 'CONSUMER' | 'RESTAURANT' | 'COMPANY' | 'SCHOOL' | 'OTHER'

export type ClientCreateInput = Omit<Client, 'codigo' | 'ativo' | 'created_at' | 'updated_at'>
export type ClientUpdateInput = Partial<Omit<Client, 'codigo' | 'created_at' | 'updated_at'>>

// ── Customer 360 ───────────────────────────────────────
export interface Customer360 extends Client {
  total_orders: number
  total_spent: number
  average_ticket: number
  first_order_at?: string
  last_order_at?: string
  days_since_last_order?: number
  favorite_product?: string
  // FASE 8: Financial metrics
  paid_amount?: number
  outstanding_balance?: number
  pending_amount?: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// ── Product (Backend: /products/) ───────────────────────
export interface Product {
  codigo: string
  nome: string
  tipo: string
  preco: number
  estoque: number
  ativo: boolean
  created_at: string
  updated_at: string
}

export type ProductCreateInput = Omit<Product, 'codigo' | 'ativo' | 'created_at' | 'updated_at'>
export type ProductUpdateInput = Partial<Omit<Product, 'codigo' | 'created_at' | 'updated_at'>>

// ── Order Item ──────────────────────────────────────────
export interface OrderItem {
  id: number
  product_codigo: string
  product_nome: string
  quantity: number
  unit_price: number
  subtotal: number
  created_at: string
}

export interface OrderItemCreate {
  product_codigo: string
  quantity: number
}

// ── Order ───────────────────────────────────────────────
export type OrderStatus =
  | 'PENDING'
  | 'CONFIRMED'
  | 'PREPARING'
  | 'DELIVERING'
  | 'DELIVERED'
  | 'CANCELLED'

export type PaymentStatus =
  | 'PENDING'
  | 'AUTHORIZED'
  | 'PAID'
  | 'FAILED'
  | 'REFUNDED'
  | 'PARTIAL'

export type OrderSource =
  | 'WHATSAPP'
  | 'PHONE'
  | 'WEB'
  | 'COUNTER'
  | 'MANUAL'
  | 'API'

export interface Order {
  codigo: string
  client_codigo: string
  subtotal: number
  delivery_fee: number
  discount: number
  total: number
  payment_method?: string
  payment_status: PaymentStatus
  address_snapshot: string
  delivery_driver_codigo?: string
  status: OrderStatus
  source: OrderSource
  notes?: string
  created_at: string
  updated_at?: string
}

export interface OrderDetail extends Order {
  items: OrderItem[]
}

export interface OrderCreateInput {
  client_codigo: string
  items: OrderItemCreate[]
  delivery_fee?: number
  discount?: number
  payment_method?: string
  source?: OrderSource
  notes?: string
}

// ── Inventory (Backend: /inventory/) ──────────────────
export type StockStatus = 'IN_STOCK' | 'LOW_STOCK' | 'OUT_OF_STOCK'

export interface InventoryItem {
  product_codigo: string
  quantity: number
  minimum_quantity: number
  maximum_quantity?: number
  stock_status: StockStatus
  available_quantity: number
  updated_at?: string
}

export interface StockMovement {
  id: number
  product_codigo: string
  type: string
  quantity: number
  reason: string
  reference_type?: string
  reference_id?: string
  balance_before: number
  balance_after: number
  created_at?: string
  created_by?: string
}

export interface ProductWithInventory {
  codigo: string
  nome: string
  tipo: string
  preco: number
  ativo: boolean
  quantity: number
  minimum_quantity: number
  stock_status: StockStatus
}

// ── Delivery Driver ─────────────────────────────────────
export interface DeliveryDriver {
  codigo: string
  nome: string
  telefone: string
  placa?: string
  ativo: boolean
  created_at: string
}

// ── WhatsApp ────────────────────────────────────────────
export type WhatsAppConnectionState = 'disconnected' | 'connecting' | 'qr_pending' | 'connected'

export interface WhatsAppStatus {
  state: WhatsAppConnectionState
  connected: boolean
  hasQr: boolean
}

// ── Auth ────────────────────────────────────────────────
export interface User {
  id: string
  email: string
  name: string
  role: UserRole
}

export type UserRole = 'ADMIN' | 'MANAGER' | 'OPERATOR' | 'DRIVER' | 'CUSTOMER' | 'SYSTEM'

// ── Delivery ───────────────────────────────────────────
export type DeliveryStatus =
  | 'PENDING'
  | 'ASSIGNED'
  | 'DISPATCHED'
  | 'EN_ROUTE'
  | 'ARRIVED'
  | 'DELIVERED'
  | 'FAILED'
  | 'CANCELLED'
  | 'RESCHEDULED'

export type DeliveryFailureReason =
  | 'CUSTOMER_ABSENT'
  | 'ADDRESS_INVALID'
  | 'REFUSED'
  | 'DAMAGED'
  | 'VEHICLE_FAILURE'
  | 'WEATHER'
  | 'OTHER'

export interface DeliveryAddress {
  street: string
  number: string
  complement: string
  neighborhood: string
  city: string
  state: string
  zip_code: string
  reference: string
}

export interface DeliveryTimelineEvent {
  status: DeliveryStatus
  timestamp: string
  actor_type: string
  notes: string
}

export interface Delivery {
  id: string
  order_id: string
  tenant_id: string
  status: DeliveryStatus
  customer_codigo: string
  customer_name: string
  driver_id: string | null
  vehicle_id: string | null
  route_id: string | null
  scheduled_at: string | null
  started_at: string | null
  arrived_at: string | null
  delivered_at: string | null
  failed_at: string | null
  failed_reason: DeliveryFailureReason | null
  failure_notes: string
  notes: string
  created_at: string
  updated_at: string
  address: DeliveryAddress
  timeline: DeliveryTimelineEvent[]
  eta_minutes: number | null
}

export interface DeliveryDriverExtended {
  id: string
  tenant_id: string
  name: string
  phone: string
  status: string
  active: boolean
  vehicle_id: string | null
  license_number: string | null
  is_available: boolean
  is_online: boolean
  has_location: boolean
  last_seen: string | null
  created_at: string
  updated_at: string
}

// ── Finance Payment (finance.py) ────────────────────────
export type FinancePaymentStatus = 'PENDING' | 'PAID' | 'PARTIAL' | 'FAILED' | 'REFUNDED'

export interface FinancePayment {
  id: number
  order_codigo: string
  amount: number
  method: string
  status: FinancePaymentStatus
  paid_at: string | null
  reference: string | null
  idempotency_key: string | null
  notes: string | null
  created_at: string
}

// ── Receivable ─────────────────────────────────────────
export type ReceivableStatus = 'OPEN' | 'PARTIAL' | 'PAID' | 'OVERDUE' | 'CANCELLED'

export interface Receivable {
  id: number
  customer_codigo: string
  order_codigo: string
  original_amount: number
  paid_amount: number
  remaining_amount: number
  due_date: string | null
  status: ReceivableStatus
  created_at: string
  settled_at: string | null
}

// ── Finance Expense ────────────────────────────────────
export interface FinanceExpense {
  id: number
  description: string
  amount: number
  category: string
  date: string
  payment_method: string | null
  notes: string | null
  status: string
  created_at: string
}

// ── Cash Movement ──────────────────────────────────────
export interface CashMovement {
  id: number
  type: string
  amount: number
  description: string
  reference_type: string | null
  reference_id: string | null
  balance_after: number
  created_at: string
}

// ── Dashboard ───────────────────────────────────────────
export interface DashboardStats {
  totalOrders: number
  pendingOrders: number
  totalRevenue: number
  totalClients: number
  totalProducts: number
  activeDrivers: number
}
