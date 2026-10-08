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

export interface SeedExpenseOverrides {
  description?: string
  amount?: number
  /** ExpenseCategory do backend: FUEL | MAINTENANCE | SUPPLIES | UTILITIES | SALARY | TAX | OTHER */
  category?: string
  /** ISO (YYYY-MM-DD ou datetime). Default: agora (cai no preset de 30 dias). */
  date?: string
}

export interface SeededExpense {
  id: number
  description: string
}

/**
 * Create an expense via the real API so a finance section has data to render.
 *
 * Deterministic by default (fixed description/amount/category) so screenshots
 * and assertions stay comparable between runs. Pass `description` when the
 * test needs a unique string (server-side `q` search).
 */
export async function seedExpense(
  request: APIRequestContext,
  token: string,
  overrides: SeedExpenseOverrides = {},
): Promise<SeededExpense> {
  const data = {
    description: 'Despesa seed E2E',
    amount: 250,
    category: 'FUEL',
    ...overrides,
  }
  const res = await request.post('/api/finance/expenses', {
    headers: auth(token),
    data,
  })
  if (res.status() !== 200) {
    throw new Error(`seedExpense: HTTP ${res.status()} ${await res.text()}`)
  }
  const body = (await res.json()) as { expense: { id: number } }
  return { id: body.expense.id, description: data.description }
}

export interface SeededReceivable {
  orderCodigo: string
  total: number
  customerNome: string
}

/**
 * Create a CONFIRMED order so it has an OPEN receivable.
 *
 * Confirming is what materializes the receivable (UpdateOrderStatusUseCase →
 * CreateReceivableUseCase) — the API deliberately exposes no receivable
 * endpoint. Deterministic: fixed product price (R$ 120), quantity 1, no
 * delivery fee, so the UI assertions can expect "R$ 120,00".
 */
export async function seedReceivable(
  request: APIRequestContext,
  token: string,
): Promise<SeededReceivable> {
  const customer = await seedCustomer(request, token)
  const product = await seedProduct(request, token)

  const orderRes = await request.post('/api/orders/', {
    headers: auth(token),
    data: {
      client_codigo: customer.codigo,
      items: [{ product_codigo: product.codigo, quantity: 1 }],
    },
  })
  if (orderRes.status() !== 200) {
    throw new Error(`seedReceivable: criar pedido HTTP ${orderRes.status()} ${await orderRes.text()}`)
  }
  const order = (await orderRes.json()) as { codigo: string; total: number }

  const confirm = await request.patch(`/api/orders/${order.codigo}/status`, {
    headers: auth(token),
    data: { status: 'CONFIRMED' },
  })
  if (confirm.status() !== 200) {
    throw new Error(`seedReceivable: confirmar pedido HTTP ${confirm.status()} ${await confirm.text()}`)
  }

  return { orderCodigo: order.codigo, total: order.total, customerNome: customer.nome }
}
