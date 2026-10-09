import { describe, it, expect } from 'vitest'
import { formatCurrency, formatDate, formatPhone, formatAxisCurrency, cn } from './utils'

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })

  it('handles conditional classes', () => {
    const shouldInclude = false
    expect(cn('foo', shouldInclude && 'bar')).toBe('foo')
    expect(cn('foo', !shouldInclude && 'bar')).toBe('foo bar')
  })
})

describe('formatCurrency', () => {
  it('formats Brazilian Real', () => {
    expect(formatCurrency(89.9)).toContain('89')
    expect(formatCurrency(0)).toContain('0')
  })
})

describe('formatAxisCurrency', () => {
  it('mantém o formato cheio abaixo de R$ 1 mil', () => {
    expect(formatAxisCurrency(0)).toBe('R$ 0')
    // Intl usa espaço não separável (R$ 500,00) — referência é o próprio formatCurrency.
    expect(formatAxisCurrency(500)).toBe(formatCurrency(500))
  })

  it('compacta mil, milhões e bilhões', () => {
    expect(formatAxisCurrency(1000)).toBe('R$ 1 mil')
    expect(formatAxisCurrency(1500)).toBe('R$ 1,5 mil')
    expect(formatAxisCurrency(2_000_000)).toBe('R$ 2 mi')
    expect(formatAxisCurrency(3_000_000_000)).toBe('R$ 3 bi')
  })

  it('preserva o sinal de negativo com o traço tipográfico', () => {
    expect(formatAxisCurrency(-1500)).toBe('−R$ 1,5 mil')
  })
})

describe('formatDate', () => {
  it('formats date string', () => {
    const result = formatDate('2026-08-26T10:30:00')
    expect(result).toBeTruthy()
  })
})

describe('formatPhone', () => {
  it('formats 11-digit phone', () => {
    const result = formatPhone('11999998888')
    expect(result).toBe('(11) 99999-8888')
  })

  it('formats 10-digit phone', () => {
    const result = formatPhone('1199999888')
    expect(result).toBe('(11) 9999-9888')
  })

  it('returns original for short numbers', () => {
    const result = formatPhone('123')
    expect(result).toBe('123')
  })
})
