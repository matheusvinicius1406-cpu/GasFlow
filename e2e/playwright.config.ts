import { defineConfig, devices } from '@playwright/test'

/**
 * E2E — GasFlow
 *
 * Targets the real full stack served by docker-compose.e2e.yml:
 * nginx (frontend, :8080) → backend → PostgreSQL. All flows go through
 * the same public entry point a browser uses (/api is stripped by nginx).
 *
 * Run:
 *   docker compose -f ../docker-compose.e2e.yml up -d --build
 *   npm ci && npx playwright install chromium
 *   npm test
 */
export default defineConfig({
  testDir: './tests',
  globalSetup: './global-setup.ts',
  fullyParallel: false,
  workers: 1, // shared DB — serial execution avoids cross-test interference
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : [['list']],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8080',
    // Sessão de admin logada uma única vez no global-setup (evita 429 do
    // rate limiter de login ao logar por teste).
    storageState: '.auth/admin.json',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // Firefox/WebKit podem ser adicionados com `npx playwright install firefox webkit`
  ],
})
