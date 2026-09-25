import { test, expect, type Page } from '@playwright/test'
import { ADMIN_PASSWORD, ADMIN_USER, uid } from './helpers'

/**
 * E2E-12: Central Financeira (P12 / Fase 5)
 *
 * Valida o estado final da consolidação (docs/auditoria/central-financeira-fase2.md §6):
 * login → menu com UMA entrada → `/finance` abre → presets (inclusive 180) →
 * seções/deep-link → criar despesa → redirects de `/reports` e `/reports/heatmap`
 * sem 404 → botão Imprimir cai no fallback → modo TV entra/sai.
 *
 * A sessão de admin vem do global-setup (storageState); só o primeiro teste faz
 * login pela UI de verdade, porque o rate limiter de login é 5 tentativas/5 min.
 */

/** Grupo das seções (as abas de navegação da própria Central). */
function secoes(page: Page) {
  return page.getByRole('group', { name: 'Seções da Central Financeira' })
}

/** Sidebar de desktop visível (a do mobile fica `hidden` em telas ≥ md). */
function sidebar(page: Page) {
  return page.locator('aside:visible')
}

test.describe('E2E-12: Central Financeira — login e menu final', () => {
  // Estado limpo: este caso exercita o login real pela UI.
  test.use({ storageState: { cookies: [], origins: [] } })

  test('login pela UI e menu com uma única entrada "Financeiro"', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Usuário').fill(ADMIN_USER)
    await page.getByLabel('Senha').fill(ADMIN_PASSWORD)
    await page.getByRole('button', { name: 'Entrar' }).click()

    await expect(page).toHaveURL(/\/$/)

    // Menu final (P11): item único "Financeiro"; o grupo velho e os links de
    // relatórios/mapa de calor não existem mais.
    const nav = sidebar(page)
    await expect(nav.getByRole('link', { name: 'Financeiro', exact: true })).toHaveCount(1)
    await expect(nav.getByText('Financeiro & Relatórios')).toHaveCount(0)
    await expect(nav.getByRole('link', { name: 'Relatórios', exact: true })).toHaveCount(0)
    await expect(nav.getByRole('link', { name: 'Mapa de Calor', exact: true })).toHaveCount(0)
    await expect(nav.getByRole('link', { name: 'Central Financeira', exact: true })).toHaveCount(0)

    // O menu leva à rota final, com guard finance.read.
    await nav.getByRole('link', { name: 'Financeiro', exact: true }).click()
    await expect(page).toHaveURL(/\/finance$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Central Financeira' })).toBeVisible()
  })
})

test.describe('E2E-12: Central Financeira — presets, seções e escritas', () => {
  test('presets de período, inclusive 180 dias', async ({ page }) => {
    await page.goto('/finance')
    await expect(page.getByRole('heading', { level: 1, name: 'Central Financeira' })).toBeVisible()

    const periodo = page.getByRole('group', { name: 'Período da Central Financeira' })
    await expect(periodo.getByRole('button', { name: '30 dias' })).toHaveAttribute('aria-pressed', 'true')

    await periodo.getByRole('button', { name: '180 dias' }).click()
    await expect(periodo.getByRole('button', { name: '180 dias' })).toHaveAttribute('aria-pressed', 'true')
    await expect(periodo.getByRole('button', { name: '30 dias' })).toHaveAttribute('aria-pressed', 'false')

    // O subtítulo confirma que o período de 180 dias foi aplicado de fato.
    await expect(page.getByText(/· 180 dias/)).toBeVisible()
  })

  test('cada seção abre com o seu título e atualiza o deep-link ?secao=', async ({ page }) => {
    await page.goto('/finance')

    const botoes = secoes(page).getByRole('button')
    const total = await botoes.count()
    // 15 seções com audit.view; 14 sem (Auditoria fica oculta sem a permissão).
    expect(total).toBeGreaterThanOrEqual(14)

    for (let i = 0; i < total; i++) {
      const botao = botoes.nth(i)
      const label = ((await botao.textContent()) ?? '').trim()
      await botao.click()
      await expect(page).toHaveURL(/secao=/)
      await expect(
        page.getByRole('heading', { level: 2, name: label, exact: true })
      ).toBeVisible()
    }

    // Deep-link direto também abre a seção certa.
    await page.goto('/finance?secao=conciliacao')
    await expect(page.getByRole('heading', { level: 2, name: 'Conciliação', exact: true })).toBeVisible()
  })

  test('cria uma despesa pela UI e ela aparece na tabela', async ({ page }) => {
    await page.goto('/finance')

    const tabela = page.getByTestId('vg-tabela')
    await expect(tabela).toBeVisible()

    // Aba Despesas antes de criar: o refresh pós-escrita mantém a aba ativa.
    await page
      .getByRole('group', { name: 'Tipo de movimentação' })
      .getByRole('button', { name: 'Despesas' })
      .click()

    const descricao = uid('Despesa E2E')
    await page.getByRole('button', { name: 'Nova despesa' }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('heading', { name: 'Nova despesa' })).toBeVisible()
    await dialog.getByLabel('Descrição da despesa').fill(descricao)
    await dialog.getByLabel('Valor da despesa em reais').fill('42.5')
    await dialog.getByRole('button', { name: 'Registrar' }).click()

    // Sucesso fecha o Dialog (nunca window.confirm) e recarrega a lista.
    await expect(dialog).toHaveCount(0)
    await expect(page.getByRole('alert').filter({ hasText: 'Despesa registrada' })).toBeVisible()

    // Busca no servidor (q em description) e confirma a linha na tabela.
    await page.getByLabel('Buscar movimentações').fill(descricao)
    await expect(tabela.getByText(descricao, { exact: true })).toBeVisible()
  })
})

test.describe('E2E-12: Central Financeira — redirects, impressão e modo TV', () => {
  test('redirects de /reports e /reports/heatmap não dão 404', async ({ page }) => {
    await page.goto('/reports')
    await expect(page).toHaveURL(/\/finance$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Central Financeira' })).toBeVisible()

    await page.goto('/reports/heatmap')
    await expect(page).toHaveURL(/\/finance\?secao=mapa-de-calor/)
    await expect(
      page.getByRole('heading', { level: 2, name: 'Mapa de Calor', exact: true })
    ).toBeVisible()
  })

  test('botão Imprimir usa o fallback do navegador', async ({ page }) => {
    await page.goto('/finance')

    // Sem a ponte do Electron, `exportCurrentViewPdf()` cai em `window.print()`.
    await page.evaluate(() => {
      const w = window as unknown as { __printCount?: number }
      w.__printCount = 0
      window.print = () => {
        w.__printCount = (w.__printCount ?? 0) + 1
      }
    })

    await page.getByRole('button', { name: 'Imprimir' }).click()

    await expect
      .poll(() => page.evaluate(() => (window as unknown as { __printCount?: number }).__printCount))
      .toBe(1)
    await expect(
      page.getByRole('alert').filter({ hasText: 'Abrindo a impressão do sistema' })
    ).toBeVisible()
  })

  test('modo TV entra e sai com ESC', async ({ page }) => {
    await page.goto('/finance')

    const botao = page.getByRole('button', { name: 'Modo TV' })
    await expect(botao).toHaveAttribute('aria-pressed', 'false')

    await botao.click()
    await expect(botao).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByText('Modo TV · Visão Geral · ESC para sair')).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(botao).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByText('Modo TV · Visão Geral · ESC para sair')).toHaveCount(0)
  })
})
