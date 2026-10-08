import { expect, test } from '@playwright/test'
import { _electron as electron, type ElectronApplication } from 'playwright'
import { copyFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { ADMIN_PASSWORD, ADMIN_USER, adminToken, seedExpense, seedReceivable } from '../tests/helpers'

/**
 * Evidência 09 — a impressão da Central Financeira com o printToPDF do app.
 *
 * Roda o desktop de verdade (dist/main + preload + handler `reports:export-pdf`
 * + gate `finance.export_pdf`) via Playwright `_electron`, apontado para o
 * stack E2E do docker-compose. O harness `desktop/scripts/evidence-pdf-harness.js`
 * só isola o userData (não toca no app instalado da máquina), desliga
 * WhatsApp/impressão e redireciona o gate IPC para o stack.
 *
 * Sai: docs/auditoria/central-financeira-fase5-evidencias/09-impressao-electron.pdf
 */

const REPO = join(__dirname, '..', '..')
const DESKTOP = join(REPO, 'desktop')
const OUT = join(REPO, 'docs', 'auditoria', 'central-financeira-fase5-evidencias')
const HARNESS = join(DESKTOP, 'scripts', 'evidence-pdf-harness.js')

function electronPath(): string {
  const bin = readFileSync(join(DESKTOP, 'node_modules', 'electron', 'path.txt'), 'utf-8').trim()
  return join(DESKTOP, 'node_modules', 'electron', 'dist', bin)
}

/** Espera o handler gravar o PDF em tmp (o harness captura shell.openPath). */
async function esperarPdf(app: ElectronApplication, timeoutMs = 60_000): Promise<string> {
  const fim = Date.now() + timeoutMs
  while (Date.now() < fim) {
    const path = await app.evaluate(
      () => (globalThis as { __openedPdf?: string | null }).__openedPdf ?? null,
    )
    if (path) return path
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error('printToPDF não gravou nenhum PDF em 60 s')
}

test('impressão da Central Financeira vira PDF pelo printToPDF do Electron', async ({ request }) => {
  test.setTimeout(240_000)

  // Base com dado real (mesmos seeds das outras evidências).
  const token = await adminToken()
  await seedExpense(request, token)
  await seedReceivable(request, token)

  const exec = electronPath()
  expect(existsSync(exec), `binário do Electron: ${exec}`).toBe(true)
  expect(existsSync(HARNESS), `harness: ${HARNESS}`).toBe(true)

  const app = await electron.launch({ executablePath: exec, args: [HARNESS], cwd: DESKTOP })
  try {
    const page = await app.firstWindow({ timeout: 90_000 })
    page.setDefaultTimeout(60_000)

    // userData isolado = sem sessão → login real pela UI (rate limiter: 1 tentativa).
    await page.getByLabel('Usuário').fill(ADMIN_USER)
    await page.getByLabel('Senha').fill(ADMIN_PASSWORD)
    await page.getByRole('button', { name: 'Entrar' }).click()
    await page.waitForURL(/\/$/)

    // Mesmo caminho do E2E: sidebar → Financeiro → /finance.
    await page.locator('aside:visible').getByRole('link', { name: 'Financeiro', exact: true }).click()
    await page.waitForURL(/\/finance$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Central Financeira' })).toBeVisible()
    await expect(page.getByTestId('vg-tabela')).toBeVisible()

    // Imprimir → ponte `window.gasflow.exportCurrentViewPdf` → IPC
    // `reports:export-pdf` → gate finance.export_pdf → printToPDF da view.
    await page.getByRole('button', { name: 'Imprimir' }).click()

    let pdfPath: string
    try {
      pdfPath = await esperarPdf(app)
    } catch (erro) {
      // Diagnóstico: o que o renderer avisou (gate negado, toast de falha…)
      // e o que o harness viu de diálogo nativo.
      const alertas = await page
        .getByRole('alert')
        .allInnerTexts()
        .catch(() => [] as string[])
      const dialogs = await app.evaluate(
        () => (globalThis as { __evidenceDialogs?: string[] }).__evidenceDialogs ?? [],
      )
      throw new Error(`${(erro as Error).message}\nalertas: ${JSON.stringify(alertas)}\ndiálogos: ${JSON.stringify(dialogs)}`)
    }
    expect(existsSync(pdfPath)).toBe(true)

    const bytes = readFileSync(pdfPath)
    expect(bytes.subarray(0, 5).toString('latin1')).toBe('%PDF-')
    expect(bytes.length, 'PDF vazio ou truncado').toBeGreaterThan(10_000)

    mkdirSync(OUT, { recursive: true })
    copyFileSync(pdfPath, join(OUT, '09-impressao-electron.pdf'))

    // O caminho do app é o "pdf"; se tivesse caído no fallback do navegador
    // (window.print) o handler não teria gravado nada e o alert abaixo aparecia.
    await expect(
      page.getByRole('alert').filter({ hasText: 'Falha ao gerar o PDF' })
    ).toHaveCount(0)

    // Diálogos nativos (consentimento da IA etc.) são auto-recusados pelo
    // harness; registramos para diagnóstico sem derrubar a evidência.
    const dialogs = await app.evaluate(
      () => (globalThis as { __evidenceDialogs?: string[] }).__evidenceDialogs ?? [],
    )
    if (dialogs.length > 0) {
      console.log('diálogos nativos auto-recusados pelo harness:', dialogs)
    }
  } finally {
    await app.close()
  }
})
