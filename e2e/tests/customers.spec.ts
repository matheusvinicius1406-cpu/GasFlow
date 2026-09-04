import { test, expect } from '@playwright/test'
import { uid, uidPhone } from './helpers'

test.describe('E2E-05: Clientes', () => {
  test('cria cliente pela UI e vê o detalhe', async ({ page }) => {
    const nome = uid('Cliente E2E')

    // Sessão já autenticada (storageState) — navega para clientes → novo
    await page.goto('/customers')
    await page.getByRole('link', { name: 'Novo Cliente' }).first().click()
    await expect(page).toHaveURL(/\/customers\/new/)

    // Preenche o formulário (placeholders/labels reais)
    await page.getByPlaceholder('Nome do cliente').fill(nome)
    await page.getByLabel('Telefone *').fill(uidPhone())
    await page.getByPlaceholder('Nome da rua').fill('Rua dos E2E')
    await page.getByPlaceholder('Número').fill('42')
    await page.getByPlaceholder('Bairro').fill(uid('Centro'))

    await page.getByRole('button', { name: /Salvar/ }).click()

    // Redireciona para o detalhe com o nome no título
    await expect(page).toHaveURL(/\/customers\/[A-Z0-9-]+$/)
    await expect(page.getByRole('heading', { level: 1 })).toContainText(nome)
  })
})
