/**
 * GasFlow Centralized Status System
 *
 * Single source of truth for all status labels, colors, and icons.
 * Eliminates STATUS_CONFIG duplication across components.
 */

export type StatusVariant = 'success' | 'warning' | 'destructive' | 'secondary' | 'default' | 'info'

export interface StatusConfig {
  label: string
  variant: StatusVariant
  color: string // Tailwind color class for text
  bgColor: string // Tailwind color class for background
}

// ── Order Statuses ─────────────────────────────────────────

export const ORDER_STATUS: Record<string, StatusConfig> = {
  PENDING:     { label: 'Novo',          variant: 'info',        color: 'text-blue-600',    bgColor: 'bg-blue-100 dark:bg-blue-900/30' },
  CONFIRMED:   { label: 'Confirmado',    variant: 'warning',     color: 'text-yellow-600',  bgColor: 'bg-yellow-100 dark:bg-yellow-900/30' },
  PREPARING:   { label: 'Preparando',    variant: 'warning',     color: 'text-yellow-600',  bgColor: 'bg-yellow-100 dark:bg-yellow-900/30' },
  DELIVERING:  { label: 'Em entrega',    variant: 'info',        color: 'text-blue-600',    bgColor: 'bg-blue-100 dark:bg-blue-900/30' },
  DELIVERED:   { label: 'Entregue',      variant: 'success',     color: 'text-green-600',   bgColor: 'bg-green-100 dark:bg-green-900/30' },
  CANCELLED:   { label: 'Cancelado',     variant: 'destructive', color: 'text-red-600',     bgColor: 'bg-red-100 dark:bg-red-900/30' },
}

// ── Delivery Statuses ──────────────────────────────────────

export const DELIVERY_STATUS: Record<string, StatusConfig> = {
  PENDING:              { label: 'Pendente',            variant: 'secondary',   color: 'text-gray-600',     bgColor: 'bg-gray-100 dark:bg-gray-900/30' },
  ASSIGNED:             { label: 'Atribuída',           variant: 'default',     color: 'text-foreground',    bgColor: 'bg-muted' },
  DISPATCHED:           { label: 'Despachada',          variant: 'default',     color: 'text-foreground',    bgColor: 'bg-muted' },
  EN_ROUTE:             { label: 'Em Rota',             variant: 'info',        color: 'text-blue-600',     bgColor: 'bg-blue-100 dark:bg-blue-900/30' },
  ARRIVED:              { label: 'Chegou',              variant: 'warning',     color: 'text-yellow-600',   bgColor: 'bg-yellow-100 dark:bg-yellow-900/30' },
  DELIVERED:            { label: 'Entregue',            variant: 'success',     color: 'text-green-600',    bgColor: 'bg-green-100 dark:bg-green-900/30' },
  FAILED:               { label: 'Falhou',              variant: 'destructive', color: 'text-red-600',      bgColor: 'bg-red-100 dark:bg-red-900/30' },
  CANCELLED:            { label: 'Cancelada',           variant: 'destructive', color: 'text-red-600',      bgColor: 'bg-red-100 dark:bg-red-900/30' },
}

// ── Payment Statuses ───────────────────────────────────────

export const PAYMENT_STATUS: Record<string, StatusConfig> = {
  PENDING:    { label: 'Pendente',     variant: 'warning',     color: 'text-yellow-600',  bgColor: 'bg-yellow-100 dark:bg-yellow-900/30' },
  AUTHORIZED: { label: 'Autorizado',   variant: 'info',        color: 'text-blue-600',    bgColor: 'bg-blue-100 dark:bg-blue-900/30' },
  PAID:       { label: 'Pago',         variant: 'success',     color: 'text-green-600',   bgColor: 'bg-green-100 dark:bg-green-900/30' },
  FAILED:     { label: 'Falhou',       variant: 'destructive', color: 'text-red-600',     bgColor: 'bg-red-100 dark:bg-red-900/30' },
  REFUNDED:   { label: 'Reembolsado',  variant: 'secondary',   color: 'text-gray-600',    bgColor: 'bg-gray-100 dark:bg-gray-900/30' },
  PARTIAL:    { label: 'Parcial',      variant: 'info',        color: 'text-blue-600',    bgColor: 'bg-blue-100 dark:bg-blue-900/30' },
}

// ── Driver Statuses ────────────────────────────────────────

export const DRIVER_STATUS: Record<string, StatusConfig> = {
  AVAILABLE:   { label: 'Disponível',    variant: 'success',     color: 'text-green-600',   bgColor: 'bg-green-100 dark:bg-green-900/30' },
  BUSY:        { label: 'Ocupado',       variant: 'warning',     color: 'text-yellow-600',  bgColor: 'bg-yellow-100 dark:bg-yellow-900/30' },
  PAUSED:      { label: 'Pausado',       variant: 'secondary',   color: 'text-gray-600',    bgColor: 'bg-gray-100 dark:bg-gray-900/30' },
  OFFLINE:     { label: 'Offline',       variant: 'secondary',   color: 'text-gray-600',    bgColor: 'bg-gray-100 dark:bg-gray-900/30' },
  UNAVAILABLE: { label: 'Indisponível',  variant: 'destructive', color: 'text-red-600',     bgColor: 'bg-red-100 dark:bg-red-900/30' },
}

// ── Inventory Statuses ─────────────────────────────────────

export const INVENTORY_STATUS: Record<string, StatusConfig> = {
  IN_STOCK:     { label: 'Em Estoque',   variant: 'success',     color: 'text-green-600',   bgColor: 'bg-green-100 dark:bg-green-900/30' },
  LOW_STOCK:    { label: 'Estoque Baixo', variant: 'warning',    color: 'text-yellow-600',  bgColor: 'bg-yellow-100 dark:bg-yellow-900/30' },
  OUT_OF_STOCK: { label: 'Sem Estoque',  variant: 'destructive', color: 'text-red-600',     bgColor: 'bg-red-100 dark:bg-red-900/30' },
}

// ── WhatsApp Conversation States ───────────────────────────

export const CONVERSATION_STATE: Record<string, StatusConfig> = {
  IDLE:                  { label: 'Ociosa',                variant: 'secondary',   color: 'text-gray-600',    bgColor: 'bg-gray-100 dark:bg-gray-900/30' },
  BROWSING:              { label: 'Navegando',             variant: 'default',     color: 'text-foreground',   bgColor: 'bg-muted' },
  BUILDING_ORDER:        { label: 'Montando Pedido',       variant: 'warning',     color: 'text-yellow-600',  bgColor: 'bg-yellow-100 dark:bg-yellow-900/30' },
  AWAITING_CONFIRMATION: { label: 'Aguardando Confirmação', variant: 'warning',    color: 'text-yellow-600',  bgColor: 'bg-yellow-100 dark:bg-yellow-900/30' },
  ORDER_CREATED:         { label: 'Pedido Criado',         variant: 'success',     color: 'text-green-600',   bgColor: 'bg-green-100 dark:bg-green-900/30' },
  HUMAN_PENDING:         { label: 'Aguardando Atendente',  variant: 'destructive', color: 'text-red-600',     bgColor: 'bg-red-100 dark:bg-red-900/30' },
  HUMAN_ACTIVE:          { label: 'Atendente Ativo',       variant: 'destructive', color: 'text-red-600',     bgColor: 'bg-red-100 dark:bg-red-900/30' },
  CLOSED:                { label: 'Fechada',               variant: 'secondary',   color: 'text-gray-600',    bgColor: 'bg-gray-100 dark:bg-gray-900/30' },
}

// ── WhatsApp Connection States ─────────────────────────────

export const WHATSAPP_STATUS: Record<string, StatusConfig> = {
  connected:    { label: 'Conectado',     variant: 'success',     color: 'text-green-600',   bgColor: 'bg-green-100 dark:bg-green-900/30' },
  connecting:   { label: 'Conectando...',  variant: 'warning',     color: 'text-yellow-600',  bgColor: 'bg-yellow-100 dark:bg-yellow-900/30' },
  qr_pending:   { label: 'Aguardando QR',  variant: 'warning',     color: 'text-yellow-600',  bgColor: 'bg-yellow-100 dark:bg-yellow-900/30' },
  disconnected: { label: 'Desconectado',   variant: 'destructive', color: 'text-red-600',     bgColor: 'bg-red-100 dark:bg-red-900/30' },
}

// ── Generic Fallback ───────────────────────────────────────

export function getStatusConfig(
  status: string,
  registry: Record<string, StatusConfig> = ORDER_STATUS
): StatusConfig {
  return registry[status] ?? {
    label: status,
    variant: 'secondary',
    color: 'text-gray-600',
    bgColor: 'bg-gray-100 dark:bg-gray-900/30',
  }
}

// ── Source Labels ──────────────────────────────────────────

export const ORDER_SOURCE_LABELS: Record<string, string> = {
  WHATSAPP: 'WhatsApp',
  PHONE: 'Telefone',
  WEB: 'Web',
  COUNTER: 'Balcão',
  MANUAL: 'Manual',
  API: 'API',
}

// ── Payment Method Labels ──────────────────────────────────

export const PAYMENT_METHOD_LABELS: Record<string, string> = {
  CASH: 'Dinheiro',
  PIX: 'PIX',
  PIX_DYNAMIC: 'PIX Dinâmico',
  CARD: 'Cartão',
  CREDIT_CARD: 'Cartão de Crédito',
  DEBIT_CARD: 'Cartão de Débito',
  TRANSFER: 'Transferência',
  ON_ACCOUNT: 'Fiado',
  OTHER: 'Outro',
}

// ── Expense Category Labels ────────────────────────────────

export const EXPENSE_CATEGORY_LABELS: Record<string, string> = {
  FUEL: 'Combustível',
  MAINTENANCE: 'Manutenção',
  SUPPLIES: 'Suprimentos',
  UTILITIES: 'Utilidades',
  SALARY: 'Salário',
  TAX: 'Imposto',
  OTHER: 'Outro',
}

// ── Movement Type Labels ───────────────────────────────────

export const MOVEMENT_TYPE_LABELS: Record<string, { label: string; color: string; isEntry: boolean }> = {
  ENTRY:           { label: 'Entrada',         color: 'text-green-600',  isEntry: true },
  SALE:            { label: 'Venda',           color: 'text-red-600',    isEntry: false },
  ADJUSTMENT:      { label: 'Ajuste',          color: 'text-blue-600',   isEntry: false },
  LOSS:            { label: 'Perda',           color: 'text-orange-600', isEntry: false },
  RETURN:          { label: 'Devolução',       color: 'text-purple-600', isEntry: true },
  INITIAL_BALANCE: { label: 'Saldo Inicial',   color: 'text-gray-600',   isEntry: true },
}
