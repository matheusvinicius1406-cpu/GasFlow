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

  // Valores
  subtotal: number
  delivery_fee: number
  discount: number
  total: number

  // Pagamento
  payment_method?: string
  payment_status: PaymentStatus

  // Entrega
  address_snapshot: string
  delivery_driver_codigo?: string

  // Status
  status: OrderStatus

  // Metadados
  source: OrderSource
  notes?: string

  // Timestamps
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

export type UserRole = 'ADMIN' | 'MANAGER' | 'ATTENDANT' | 'DISPATCHER' | 'DRIVER'

// ── Dashboard ───────────────────────────────────────────
export interface DashboardStats {
  totalOrders: number
  pendingOrders: number
  totalRevenue: number
  totalClients: number
  totalProducts: number
  activeDrivers: number
}
