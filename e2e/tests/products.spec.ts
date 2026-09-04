import { test, expect } from '@playwright/test'
import { uid } from './helpers'

test.describe('E2E-04: Produtos', () => {
  test('cria produto pela UI e vê o detalhe', async ({ page }) => {
    const nome = uid('Gás P13 E2E')

    // Sessão já autenticada (storageState) — navega para produtos → novo
    await page.goto('/products')
    await page.getByRole('link', { name: 'Novo Produto' }).first().click()
    await expect(page).toHaveURL(/\/products\/new/)

    // Preenche o formulário
    await page.getByPlaceholder('Ex: Gás P13, Água 20L').fill(nome)
    await page.getByLabel('Tipo *').selectOption('GAS')
    await page.getByLabel(/Preço/).fill('150')
    await page.getByLabel(/Estoque/).fill('30')

    await page.getByRole('button', { name: /Salvar/ }).click()

    // Redireciona para o detalhe com o nome no título
    await expect(page).toHaveURL(/\/products\/[A-Z0-9-]+$/)
    await expect(page.getByRole('heading', { level: 1 })).toContainText(nome)
  })
})
