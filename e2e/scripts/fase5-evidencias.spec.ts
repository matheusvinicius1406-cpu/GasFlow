import { expect, test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { adminToken, seedExpense, seedReceivable } from '../tests/helpers'

/**
 * Evidências da Fase 5 — screenshots gerados contra o stack real.
 *
 * Roda na config separada (`npm run evidencias`), nunca na suíte de CI.
 * Base determinística: 2 despesas + 2 recebíveis (um em aberto, um quitado),
 * todos os dados reais da API — nada é injetado no DOM.
 *
 * Capturas (lista sugerida no §5 de docs/auditoria/central-financeira-fase5.md):
 *   01 Visão Geral 30 dias        05 Conciliação (P8)
 *   02 Visão Geral 180 dias       06 aba Recebíveis (fix da Fase 8)
 *   03 DRE (P6)                   07 impressão (@media print)
 *   04 Clientes (P7, aging)       08 modo TV
 */

const OUT = join(__dirname, '..', '..', 'docs', 'auditoria', 'central-financeira-fase5-evidencias')

function secoes(page: Page) {
  return page.getByRole('group', { name: 'Seções da Central Financeira' })
}

async function shot(page: Page, arquivo: string, cheio = true) {
  await page.screenshot({ path: join(OUT, arquivo), fullPage: cheio })
}

async function abrirSecao(page: Page, label: string, arquivo: string) {
  await secoes(page).getByRole('button', { name: label, exact: true }).click()
  await expect(page.getByRole('heading', { level: 2, name: label, exact: true })).toBeVisible()
  // Os gráficos (canvas/svg) montam depois do h2; deixa a seção assentar antes
  // de fotografar — é captura de evidência, não asserção de timing.
  await page.waitForTimeout(800)
  await shot(page, arquivo)
}

test('evidências da Fase 5: seções, impressão e modo TV', async ({ page, request }) => {
  mkdirSync(OUT, { recursive: true })
  const token = await adminToken()
  const auth = { Authorization: `Bearer ${token}` }

  // --- base determinística (API real, mesma ponte do navegador) ---
  await seedExpense(request, token)
  await seedExpense(request, token, {
    description: 'Despesa seed E2E — manutenção',
    amount: 180,
    category: 'MAINTENANCE',
  })
  const aberto = await seedReceivable(request, token)
  const quitado = await seedReceivable(request, token)
  const pagamento = await request.post(`/api/finance/orders/${quitado.orderCodigo}/payments`, {
    headers: auth,
    data: { amount: quitado.total, method: 'PIX' },
  })
  expect(pagamento.status()).toBe(200)

  // --- 01/02: Visão Geral nos dois presets ---
  await page.goto('/finance')
  await expect(page.getByRole('heading', { level: 1, name: 'Central Financeira' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: 'Visão Geral' })).toBeVisible()
  await expect(page.getByTestId('vg-tabela')).toBeVisible()
  await shot(page, '01-visao-geral-30d.png')

  const periodo = page.getByRole('group', { name: 'Período da Central Financeira' })
  await periodo.getByRole('button', { name: '180 dias' }).click()
  await expect(page.getByText(/· 180 dias/)).toBeVisible()
  await page.waitForTimeout(800)
  await shot(page, '02-visao-geral-180d.png')

  // --- 03/04/05: uma seção analítica por PR (P6, P7, P8) ---
  await abrirSecao(page, 'DRE', '03-secao-dre.png')
  await abrirSecao(page, 'Clientes', '04-secao-clientes.png')
  await abrirSecao(page, 'Conciliação', '05-secao-conciliacao.png')

  // --- 06: aba Recebíveis (título em aberto = fix da Fase 8) ---
  await page.goto('/finance')
  await expect(page.getByTestId('vg-tabela')).toBeVisible()
  await page
    .getByRole('group', { name: 'Tipo de movimentação' })
    .getByRole('button', { name: 'Recebíveis' })
    .click()
  await expect(page.getByRole('row').filter({ hasText: `#${aberto.orderCodigo}` })).toBeVisible()
  await page.waitForTimeout(500)
  await shot(page, '06-recebiveis-aba.png')

  // --- 07: layout de impressão (sidebar/header ocultos, .print-only visível) ---
  await page.goto('/finance')
  await expect(page.getByTestId('vg-tabela')).toBeVisible()
  await page.emulateMedia({ media: 'print' })
  await page.waitForTimeout(500)
  await shot(page, '07-impressao-visao-geral.png', false)
  await page.emulateMedia({ media: null })

  // --- 08: modo TV ---
  await page.getByRole('button', { name: 'Modo TV' }).click()
  await expect(page.getByText('Modo TV · Visão Geral · ESC para sair')).toBeVisible()
  await page.waitForTimeout(800)
  await shot(page, '08-modo-tv.png', false)
  await page.keyboard.press('Escape')
})

test('sanidade: as 8 capturas foram gravadas', async () => {
  const { readdirSync } = await import('node:fs')
  const arquivos = readdirSync(OUT).filter((f) => f.endsWith('.png'))
  expect(arquivos.sort()).toEqual([
    '01-visao-geral-30d.png',
    '02-visao-geral-180d.png',
    '03-secao-dre.png',
    '04-secao-clientes.png',
    '05-secao-conciliacao.png',
    '06-recebiveis-aba.png',
    '07-impressao-visao-geral.png',
    '08-modo-tv.png',
  ])
})
