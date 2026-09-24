import { test, expect } from '@playwright/test'
import { uid, uidPhone } from './helpers'

test.describe('E2E-06: Motoristas', () => {
  test('cria motorista pela UI, recebe a credencial e volta para a lista', async ({ page }) => {
    const nome = uid('Motorista E2E')

    // Sessão já autenticada (storageState) — navega para motoristas → novo
    await page.goto('/drivers')
    await page.getByRole('link', { name: 'Novo Motorista' }).first().click()
    await expect(page).toHaveURL(/\/drivers\/new/)

    // Formulário atual: nome, telefone, placa e CNH/documento. O antigo
    // "Tipo de Veículo" era campo fantasma (não existe no request nem na
    // resposta) e saiu junto com o `vehicle_type` do backend.
    await page.getByPlaceholder('Nome do motorista').fill(nome)
    await page.getByPlaceholder('(00) 00000-0000').fill(uidPhone())
    await page.getByPlaceholder('ABC-1234').fill('E2E-2026')
    await page.getByPlaceholder('000.000.000-00').fill('12345678901')

    await page.getByRole('button', { name: /Salvar/ }).click()

    // `POST /admin/drivers` é o caminho canônico: cria a entidade **e** a
    // credencial, e a senha temporária aparece uma única vez — a tela mostra
    // a credencial em vez de navegar direto para a lista (antes o cadastro
    // saía sem login e o entregador não conseguia abrir o app).
    await expect(page.getByTestId('driver-username')).not.toBeEmpty()
    await expect(page.getByTestId('driver-temporary-password')).not.toBeEmpty()

    await page.getByRole('button', { name: 'Ir para a lista' }).click()

    // Volta para a lista de motoristas, com o recém-criado visível
    await expect(page).toHaveURL(/\/drivers$/)
    await expect(page.getByText(nome)).toBeVisible()
  })
})
