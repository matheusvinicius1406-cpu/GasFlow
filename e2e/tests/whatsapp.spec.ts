import { test, expect } from '@playwright/test'

/**
 * E2E-WA: módulo WhatsApp
 *
 * A stack E2E não inclui o serviço whatsapp (exige pareamento manual/QR).
 *
 * O módulo virou rotas aninhadas: a raiz `/whatsapp` é a página de Conversas
 * e quem fala com o serviço é `/whatsapp/accounts` ("Contas & Conexão") — é
 * lá que o estado "Serviço Indisponível" aparece de forma determinística
 * nesta stack. Antes o spec mirava abas (Contas/Conversas/Campanhas/
 * Automações) numa página única que não existe mais.
 */
test.describe('E2E-WA: módulo WhatsApp', () => {
  test('a página renderiza com as seções de gestão', async ({ page }) => {
    await page.goto('/whatsapp')
    await expect(page.getByRole('heading', { name: 'Conversas Ativas' })).toBeVisible()

    // Seções do módulo na navegação lateral (o grupo "WhatsApp" abre quando
    // a rota é do módulo).
    for (const secao of ['Conversas', 'Contatos', 'Organizador', 'Campanhas', 'Automações', 'Contas & Conexão']) {
      await expect(page.getByRole('link', { name: secao, exact: true })).toBeVisible()
    }
  })

  test('sem o serviço whatsapp na stack, mostra o estado de serviço indisponível', async ({ page }) => {
    await page.goto('/whatsapp/accounts')
    // Aparece duas vezes: título (h3) e descrição (p) — usar o heading.
    // A busca de contas tem timeout próprio antes de cair no estado de erro.
    await expect(page.getByRole('heading', { name: 'Serviço Indisponível' })).toBeVisible({ timeout: 25_000 })
    await expect(page.getByRole('button', { name: 'Tentar novamente' })).toBeVisible()
  })

  test.describe('com sessão pareada (E2E_WHATSAPP_CONNECTED=1)', () => {
    test.skip(!process.env.E2E_WHATSAPP_CONNECTED, 'requer serviço whatsapp + QR pareado na stack')

    test('a conta conectada aparece com telefone e badge Conectado', async ({ page }) => {
      await page.goto('/whatsapp/accounts')
      // As contas são carregadas em 15s; a primeira já deve estar conectada.
      await expect(page.getByText('Conectado').first()).toBeVisible({ timeout: 20000 })
      await expect(page.getByRole('button', { name: 'Desconectar' }).first()).toBeVisible()
      // A coluna "Conectadas" do resumo deve ser >= 1.
      await expect(page.getByText('Conectadas')).toBeVisible()
    })
  })
})
