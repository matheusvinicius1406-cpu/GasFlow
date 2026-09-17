import {
  CheckCircle,
  FileText,
  Pause,
  Rocket,
  X,
} from 'lucide-react'

// ── Campaign Status Config ──────────────────────────────

export const CAMPAIGN_STATUS_CONFIG: Record<
  string,
  {
    label: string
    variant: 'success' | 'warning' | 'destructive' | 'info' | 'secondary'
    icon: React.ElementType
  }
> = {
  DRAFT: { label: 'Rascunho', variant: 'secondary', icon: FileText },
  RUNNING: { label: 'Em execução', variant: 'info', icon: Rocket },
  PAUSED: { label: 'Pausada', variant: 'warning', icon: Pause },
  COMPLETED: { label: 'Concluída', variant: 'success', icon: CheckCircle },
  CANCELLED: { label: 'Cancelada', variant: 'destructive', icon: X },
  FAILED: { label: 'Falhou', variant: 'destructive', icon: X },
}

// ── Recipient Status Config ─────────────────────────────

export const RECIPIENT_STATUS_CONFIG: Record<
  string,
  { label: string; variant: 'success' | 'warning' | 'destructive' | 'info' | 'secondary' }
> = {
  PENDING: { label: 'Pendente', variant: 'secondary' },
  PROCESSING: { label: 'Processando', variant: 'info' },
  SENT: { label: 'Enviado', variant: 'success' },
  FAILED: { label: 'Falhou', variant: 'destructive' },
  CANCELLED: { label: 'Cancelado', variant: 'warning' },
}

// ── Date Formatter ──────────────────────────────────────

export function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
