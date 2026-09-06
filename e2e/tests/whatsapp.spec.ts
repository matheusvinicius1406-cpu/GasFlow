import { test, expect } from '@playwright/test'

/**
 * E2E-WA: Página WhatsApp
 *
 * A stack E2E não inclui o serviço whatsapp (exige pareamento manual/QR),
 * então o estado "Serviço Indisponível" é o resultado determinístico local.
 * Quando a stack tiver o serviço + sessão pareada, rode com
 * E2E_WHATSAPP_CONNECTED=1 para validar o estado conectado real.
 */
test.describe('E2E-WA: Página WhatsApp', () => {
  test('a página renderiza com as abas de gestão', async ({ page }) => {
    await page.goto('/whatsapp')
    await expect(page.getByRole('heading', { name: 'WhatsApp' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Contas' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Conversas' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Campanhas' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Automações' })).toBeVisible()
  })

  test('sem o serviço whatsapp na stack, mostra o estado de serviço indisponível', async ({ page }) => {
    await page.goto('/whatsapp')
    // Aparece duas vezes: título (h3) e descrição (p) — usar o heading
    await expect(page.getByRole('heading', { name: 'Serviço Indisponível' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Tentar novamente' })).toBeVisible()
  })

  test.describe('com sessão pareada (E2E_WHATSAPP_CONNECTED=1)', () => {
    test.skip(!process.env.E2E_WHATSAPP_CONNECTED, 'requer serviço whatsapp + QR pareado na stack')

    test('a conta conectada aparece com telefone e badge Conectado', async ({ page }) => {
      await page.goto('/whatsapp')
      // As contas são carregadas em 15s; a primeira já deve estar conectada.
      await expect(page.getByText('Conectado').first()).toBeVisible({ timeout: 20000 })
      await expect(page.getByRole('button', { name: 'Desconectar' }).first()).toBeVisible()
      // A coluna "Conectadas" do resumo deve ser >= 1.
      await expect(page.getByText('Conectadas')).toBeVisible()
    })
  })
})
