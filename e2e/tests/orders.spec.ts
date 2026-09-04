import { test, expect } from '@playwright/test'
import { adminToken, seedCustomer, seedProduct } from './helpers'

test.describe('E2E-02/03: Pedidos', () => {
  test('cria pedido pela UI (cliente+produto com estoque) e confirma status', async ({ page, request }) => {
    // ── Setup: cliente e produto com estoque via API real ──
    const token = await adminToken()
    const customer = await seedCustomer(request, token)
    const product = await seedProduct(request, token)

    // ── Novo pedido (sessão já autenticada via storageState) ──
    await page.goto('/orders/new')
    await expect(page).toHaveURL(/\/orders\/new/)

    // Cliente (select 1) e produto (select 2) — valores reais do seed
    await page.locator('select').nth(0).selectOption(customer.codigo)
    await page.locator('select').nth(1).selectOption(product.codigo)

    await page.getByRole('button', { name: 'Criar Pedido' }).click()

    // Redireciona para o detalhe do pedido
    await expect(page).toHaveURL(/\/orders\/[A-Z0-9-]+$/)
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Pedido #')

    // Pedido recém-criado: status "Novo" (PENDING)
    await expect(page.getByText('Novo', { exact: true })).toBeVisible()

    // ── Confirmar pedido (transição PENDING → CONFIRMED) ──
    page.once('dialog', (dialog) => dialog.accept())
    await page.getByRole('button', { name: 'Confirmar' }).click()

    await expect(page.getByText('Confirmado', { exact: true })).toBeVisible()
  })
})
