import { test, expect } from '@playwright/test'
import { uid, uidPhone } from './helpers'

test.describe('E2E-06: Motoristas', () => {
  test('cria motorista pela UI e volta para a lista', async ({ page }) => {
    const nome = uid('Motorista E2E')

    // Sessão já autenticada (storageState) — navega para motoristas → novo
    await page.goto('/drivers')
    await page.getByRole('link', { name: 'Novo Motorista' }).first().click()
    await expect(page).toHaveURL(/\/drivers\/new/)

    // Preenche o formulário
    await page.getByPlaceholder('Nome do motorista').fill(nome)
    await page.getByPlaceholder('(00) 00000-0000').fill(uidPhone())
    await page.getByPlaceholder('ABC-1234').fill('E2E-2026')
    await page.getByLabel('Tipo de Veículo').selectOption('MOTORCYCLE')

    await page.getByRole('button', { name: /Salvar/ }).click()

    // Volta para a lista de motoristas
    await expect(page).toHaveURL(/\/drivers$/)
  })
})
