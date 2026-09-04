import { test, expect } from '@playwright/test'
import { ADMIN_PASSWORD, ADMIN_USER } from './helpers'

// Estado limpo (sem sessão) para os casos que exigem não-autenticado.
test.describe('E2E-01: Autenticação — sem sessão', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('credenciais inválidas mostram erro e permanece no login', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Usuário').fill(ADMIN_USER)
    await page.getByLabel('Senha').fill('senha-errada')
    await page.getByRole('button', { name: 'Entrar' }).click()

    await expect(page.getByText('Email ou senha inválidos')).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)
  })

  test('rota protegida redireciona para /login sem sessão', async ({ page }) => {
    await page.goto('/orders')
    await expect(page).toHaveURL(/\/login/)
  })
})

test.describe('E2E-01: Autenticação — sessão ativa (storageState)', () => {
  test('sessão de admin acessa o dashboard', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Pedidos' })).toBeVisible()
  })
})
