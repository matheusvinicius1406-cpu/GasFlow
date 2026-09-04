import { expect, type APIRequestContext } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

export const ADMIN_USER = 'admin'
export const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin123'

/** Unique-ish suffix so repeated runs do not collide on names. */
export function uid(prefix: string): string {
  return `${prefix}-${Date.now()}`
}

/**
 * Return the admin token persisted by global-setup.
 *
 * Reading storageState instead of logging in again avoids the login rate
 * limiter (5 attempts/5 min) — one real login per run is enough.
 */
export async function adminToken(): Promise<string> {
  const state = JSON.parse(
    readFileSync(join(__dirname, '..', '.auth', 'admin.json'), 'utf-8'),
  ) as { origins: { localStorage: { name: string; value: string }[] }[] }
  const entry = state.origins[0].localStorage.find(
    (item) => item.name === 'gasflow_token',
  )
  if (!entry?.value) throw new Error('storageState sem gasflow_token')
  return entry.value
}

function auth(token: string) {
  return { Authorization: `Bearer ${token}` }
}

/** Unique 11-digit BR phone (backend rejects duplicate phones). */
export function uidPhone(): string {
  return `119${String(Date.now()).slice(-8)}`
}

export interface SeededCustomer {
  codigo: string
  nome: string
  bairro: string
}

/** Create a customer via the real API. */
export async function seedCustomer(
  request: APIRequestContext,
  token: string,
): Promise<SeededCustomer> {
  const nome = uid('Cliente E2E')
  const bairro = uid('Bairro')
  const res = await request.post('/api/clients/', {
    headers: auth(token),
    data: {
      nome,
      telefone: uidPhone(),
      rua: 'Rua Teste',
      numero: '123',
      bairro,
      cidade: 'Sao Paulo',
    },
  })
  expect(res.status()).toBe(200)
  const body = await res.json()
  return { codigo: body.codigo, nome, bairro }
}

export interface SeededProduct {
  codigo: string
  nome: string
}

/** Create a product via the real API AND add stock (orders require inventory). */
export async function seedProduct(
  request: APIRequestContext,
  token: string,
): Promise<SeededProduct> {
  const nome = uid('Gás P13 E2E')
  const res = await request.post('/api/products/', {
    headers: auth(token),
    data: { nome, tipo: 'GAS', preco: 120, estoque: 0 },
  })
  expect(res.status()).toBe(200)
  const body = await res.json()

  // Orders validate stock against the Inventory table, not Product.estoque
  const stock = await request.post(`/api/inventory/${body.codigo}/entries`, {
    headers: auth(token),
    data: { quantity: 50, reason: 'Seed E2E' },
  })
  expect(stock.status()).toBe(200)

  return { codigo: body.codigo, nome }
}
