import { Badge, type BadgeProps } from './Badge'
import type { OrderStatus } from '@/types'

const statusConfig: Record<string, { label: string; variant: BadgeProps['variant'] }> = {
  // Order statuses
  PENDING: { label: 'Novo', variant: 'info' },
  CONFIRMED: { label: 'Confirmado', variant: 'warning' },
  PREPARING: { label: 'Em preparação', variant: 'warning' },
  DELIVERING: { label: 'Em entrega', variant: 'info' },
  DELIVERED: { label: 'Entregue', variant: 'success' },
  CANCELLED: { label: 'Cancelado', variant: 'destructive' },

  // Delivery statuses
  AGUARDANDO_DESPACHO: { label: 'Aguardando despacho', variant: 'info' },
  ATRIBUIDA: { label: 'Atribuída', variant: 'warning' },
  EM_ROTA: { label: 'Em rota', variant: 'info' },
  CHEGOU: { label: 'Chegou', variant: 'warning' },
  FALHA: { label: 'Falha', variant: 'destructive' },
  CANCELADA: { label: 'Cancelada', variant: 'destructive' },

  // Connection statuses
  connected: { label: 'Conectado', variant: 'success' },
  connecting: { label: 'Conectando...', variant: 'warning' },
  qr_pending: { label: 'Aguardando QR', variant: 'warning' },
  disconnected: { label: 'Desconectado', variant: 'destructive' },

  // Campaign statuses
  DRAFT: { label: 'Rascunho', variant: 'secondary' },
  RUNNING: { label: 'Em execução', variant: 'info' },
  PAUSED: { label: 'Pausada', variant: 'warning' },
  COMPLETED: { label: 'Concluída', variant: 'success' },
  FAILED: { label: 'Falhou', variant: 'destructive' },
}

interface StatusBadgeProps {
  status: OrderStatus | string
  className?: string
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status] ?? { label: status, variant: 'secondary' as const }

  return (
    <Badge variant={config.variant} className={className}>
      {config.label}
    </Badge>
  )
}
