import { describe, it, expect } from 'vitest'
import { formatCurrency, formatDate, formatPhone, cn } from './utils'

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
