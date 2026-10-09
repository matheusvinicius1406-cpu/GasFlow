import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Merge Tailwind classes with clsx.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// ── Currency Formatting ────────────────────────────────────

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value)
}

/** Alias for backward compatibility */
export const formatMoney = formatCurrency

/**
 * Rótulo compacto para eixo monetário de gráfico — em vez de "R$ 1.500,00"
 * (largo demais para o tick, corta na margem), devolve "R$ 1,5 mil".
 * Abaixo de R$ 1 mil mantém o formato cheio; acima usa mil/mi/bi.
 */
export function formatAxisCurrency(value: number): string {
  const abs = Math.abs(value)
  if (value === 0) return 'R$ 0'
  if (abs < 1000) return formatCurrency(value)
  const step = abs >= 1e9 ? 1e9 : abs >= 1e6 ? 1e6 : 1e3
  const sufixo = step === 1e9 ? 'bi' : step === 1e6 ? 'mi' : 'mil'
  const numero = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 }).format(abs / step)
  return `${value < 0 ? '−' : ''}R$ ${numero} ${sufixo}`
}

// ── Number Formatting ──────────────────────────────────────

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('pt-BR').format(value)
}

export function formatPercent(value: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value / 100)
}

// ── Date Formatting ────────────────────────────────────────

export function formatDate(date: string | Date): string {
  return new Intl.DateTimeFormat('pt-BR').format(new Date(date))
}

export function formatDateTime(date: string | Date): string {
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(date))
}

export function formatTime(date: string | Date): string {
  return new Intl.DateTimeFormat('pt-BR', {
    timeStyle: 'short',
  }).format(new Date(date))
}

export function formatRelativeTime(date: string | Date): string {
  const now = new Date()
  const d = new Date(date)
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffH = Math.floor(diffMs / 3600000)
  const diffD = Math.floor(diffMs / 86400000)

  if (diffMin < 1) return 'agora'
  if (diffMin < 60) return `${diffMin}min atrás`
  if (diffH < 24) return `${diffH}h atrás`
  if (diffD < 7) return `${diffD}d atrás`
  return formatDate(date)
}

// ── Phone Formatting ───────────────────────────────────────

export function formatPhone(phone: string): string {
  const digits = phone.replace(/\D/g, '')
  if (digits.length === 11) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`
  }
  if (digits.length === 10) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`
  }
  return phone
}

// ── Address Formatting ─────────────────────────────────────

export function formatAddress(street: string, number: string, neighborhood: string): string {
  return `${street}, ${number} - ${neighborhood}`
}
