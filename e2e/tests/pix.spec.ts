import { test, expect } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { adminToken } from './helpers'

/**
 * E2E-09/10 — PIX.
 *
 * Não existe tela que gere payloads PIX (a UI de /settings apenas gerencia a
 * configuração da chave); o fluxo completo (configurar chave → gerar BR Code +
 * QR) é exercitado pela API real passando pelo mesmo nginx/backend/DB do E2E.
 */
test.describe('E2E-09/10: PIX (payload + QR)', () => {
  test('configura chave e gera payload BR Code com QR válido', async ({ request }) => {
    const token = await adminToken()
    const headers = { Authorization: `Bearer ${token}` }

    // ── 1. Configurar chave PIX (chave aleatória) ──
    const key = randomUUID()
    const create = await request.post('/api/payments/pix', {
      headers,
      data: {
        key,
        key_type: 'RANDOM',
        holder_name: 'GasFlow E2E',
        city: 'Sao Paulo',
      },
    })
    expect(create.status()).toBe(200)
    const created = await create.json()
    expect(created.success).toBe(true)

    // ── 2. Configuração aparece na listagem ──
    const list = await request.get('/api/payments/pix', { headers })
    expect(list.status()).toBe(200)
    const listed = await list.json()
    expect(listed.count).toBeGreaterThanOrEqual(1)
    const config = listed.configs.find((c: { key: string }) => c.key === key)
    expect(config).toBeTruthy()

    // ── 3. Gerar payload (BR Code + QR) ──
    const payloadRes = await request.post('/api/payments/pix/payload', {
      headers,
      data: { amount: 150.5, description: 'Pagamento E2E' },
    })
    expect(payloadRes.status()).toBe(200)
    const payload = await payloadRes.json()

    // BR Code: começa com o Payload Format Indicator (000201) e contém o
    // Merchant Account (26/br.gov.bcb.pix)
    expect(payload.br_code).toMatch(/^000201/)
    expect(payload.br_code).toContain('br.gov.bcb.pix')
    expect(payload.qr_code).toMatch(/^data:image\/png;base64,/)
    expect(payload.txid).toBeTruthy()
    expect(payload.amount).toBe(150.5)

    // ── 4. Consulta de status: NOT_FOUND até integração PSP ──
    // Contrato real: HTTP 200 com status NOT_FOUND no corpo (sem payment
    // registrado ainda); integração PSP/webhook é que preencherá PENDING/PAID.
    const statusRes = await request.get(
      `/api/payments/pix/${payload.txid}/status`,
      { headers },
    )
    expect(statusRes.status()).toBe(200)
    const statusBody = await statusRes.json()
    expect(statusBody.status).toBe('NOT_FOUND')
    expect(statusBody.txid).toBe(payload.txid)
  })
})
