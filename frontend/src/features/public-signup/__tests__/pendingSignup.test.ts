import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

import {
  MAX_AGE_MS,
  bumpAttempts,
  clearPending,
  isTransientFailure,
  loadPending,
  retryDelayMs,
  savePending,
  type SignupPayload,
} from '../pendingSignup'

function payload(overrides: Partial<SignupPayload> = {}): SignupPayload {
  return {
    inviteToken: 'GF-INV-abc123def456ghi789',
    name: 'Maria Souza',
    phone: '11988887777',
    rua: 'Rua das Flores',
    numero: '120',
    bairro: 'Jardim América',
    lgpdConsent: true,
    ...overrides,
  }
}

const TOKEN = 'GF-INV-abc123def456ghi789'

describe('pendingSignup', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('guarda e recupera o cadastro pelo token', () => {
    savePending(TOKEN, payload())

    const record = loadPending(TOKEN)
    expect(record).not.toBeNull()
    expect(record?.payload.name).toBe('Maria Souza')
    expect(record?.payload.phone).toBe('11988887777')
    expect(record?.attempts).toBe(0)
  })

  it('não devolve nada para token sem cadastro guardado', () => {
    expect(loadPending('GF-INV-outro-token-qualquer')).toBeNull()
    expect(loadPending('')).toBeNull()
  })

  it('limpa só o token pedido, preservando os outros', () => {
    savePending(TOKEN, payload())
    savePending('GF-INV-outro-token', payload({ inviteToken: 'GF-INV-outro-token' }))

    clearPending(TOKEN)

    expect(loadPending(TOKEN)).toBeNull()
    expect(loadPending('GF-INV-outro-token')).not.toBeNull()
  })

  it('incrementa as tentativas mantendo o payload', () => {
    savePending(TOKEN, payload())

    const after = bumpAttempts(TOKEN)

    expect(after?.attempts).toBe(1)
    expect(loadPending(TOKEN)?.attempts).toBe(1)
    expect(loadPending(TOKEN)?.payload.bairro).toBe('Jardim América')
    expect(bumpAttempts('GF-INV-nada-aqui')).toBeNull()
  })

  it('descarta cadastro antigo (mais de 7 dias) e mantém o recente', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T12:00:00Z'))
    savePending('GF-INV-antigo', payload({ inviteToken: 'GF-INV-antigo' }))

    // 10 dias depois: o antigo expirou, um novo segue válido
    vi.setSystemTime(new Date('2026-01-11T12:00:00Z'))
    savePending('GF-INV-novo', payload({ inviteToken: 'GF-INV-novo' }))

    expect(loadPending('GF-INV-antigo')).toBeNull()
    expect(loadPending('GF-INV-novo')).not.toBeNull()

    // Logo após o limite o registro ainda vale (não expira cedo demais)
    vi.setSystemTime(new Date(Date.parse('2026-01-11T12:00:00Z') + MAX_AGE_MS))
    expect(loadPending('GF-INV-novo')).not.toBeNull()
  })

  it('não quebra com armazenamento corrompido', () => {
    localStorage.setItem('gasflow_invite_pending', '{isso não é json')

    expect(loadPending(TOKEN)).toBeNull()
    // E ainda consegue gravar por cima
    savePending(TOKEN, payload())
    expect(loadPending(TOKEN)?.payload.name).toBe('Maria Souza')
  })

  it('classifica falha transitória (rede/5xx/limite) versus permanente', () => {
    // Rede fora / túnel caído: axiosError sem response
    expect(isTransientFailure(new Error('Network Error'))).toBe(true)
    expect(isTransientFailure({})).toBe(true)
    expect(isTransientFailure({ response: { status: 500 } })).toBe(true)
    expect(isTransientFailure({ response: { status: 503 } })).toBe(true)
    expect(isTransientFailure({ response: { status: 408 } })).toBe(true)
    expect(isTransientFailure({ response: { status: 429 } })).toBe(true)

    // Reenviar não muda nada
    expect(isTransientFailure({ response: { status: 404 } })).toBe(false)
    expect(isTransientFailure({ response: { status: 409 } })).toBe(false)
    expect(isTransientFailure({ response: { status: 422 } })).toBe(false)
  })

  it('cresce o intervalo entre reenvios até o teto', () => {
    expect(retryDelayMs(0)).toBe(3_000)
    expect(retryDelayMs(1)).toBe(8_000)
    expect(retryDelayMs(2)).toBe(20_000)
    expect(retryDelayMs(3)).toBe(60_000)
    // Não cresce indefinidamente
    expect(retryDelayMs(50)).toBe(60_000)
  })
})
