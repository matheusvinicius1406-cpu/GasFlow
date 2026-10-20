/**
 * Captura screenshots das telas principais para o README.
 * Rode com a stack dev no ar (backend :8000, frontend :5173).
 */
import { chromium } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'

const FRONTEND = process.env.FRONTEND_URL || 'http://[::1]:5173'
const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8000'
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'gasflow-dev'
const OUT = join(__dirname, '..', 'docs', 'screenshots')

const ROUTES: [string, string][] = [
  ['dashboard', '/'],
  ['orders', '/orders'],
  ['customers', '/customers'],
  ['products', '/products'],
  ['deliveries', '/deliveries'],
  ['finance', '/finance'],
  ['inventory', '/inventory'],
  ['whatsapp', '/whatsapp'],
  ['contacts', '/whatsapp/contacts'],
  ['campaigns', '/whatsapp/campaigns'],
  ['settings', '/settings'],
]

async function main() {
  mkdirSync(OUT, { recursive: true })

  // Login via API real (mesmo fluxo do e2e global-setup).
  const loginRes = await fetch(`${BACKEND}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: ADMIN_PASSWORD }),
  })
  if (!loginRes.ok) {
    console.error(`login falhou: ${loginRes.status} — tente ADMIN_PASSWORD=admin123`)
    process.exit(1)
  }
  const { token } = (await loginRes.json()) as { token: string }
  console.log('login ok')

  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1.5,
    colorScheme: 'dark',
  })
  await context.addInitScript((t) => {
    localStorage.setItem('gasflow_token', t)
  }, token)

  const page = await context.newPage()
  for (const [name, path] of ROUTES) {
    try {
      await page.goto(`${FRONTEND}${path}`, { waitUntil: 'networkidle', timeout: 30000 })
      // Espera extra para charts/tabelas hidratarem.
      await page.waitForTimeout(1500)
      await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: false })
      console.log(`ok  ${name}  ${path}`)
    } catch (e) {
      console.error(`fail ${name} ${path}: ${(e as Error).message}`)
    }
  }

  await browser.close()
  console.log(`\nscreenshots em ${OUT}`)
}

main()
