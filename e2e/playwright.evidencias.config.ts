import { defineConfig, devices } from '@playwright/test'

/**
 * Evidências da Fase 5 (Central Financeira — P12)
 *
 * Config separada da suíte: este run semeia uma base determinística e grava
 * screenshots em docs/auditoria/central-financeira-fase5-evidencias/.
 * Fica FORA do testDir padrão (./tests) de propósito — a suíte de CI não pode
 * depender de nem alterar o estado da base para "fotografar".
 *
 * Run:
 *   docker compose -f ../docker-compose.e2e.yml down -v
 *   docker compose -f ../docker-compose.e2e.yml up -d --build
 *   npm run evidencias
 */
export default defineConfig({
  testDir: './scripts',
  globalSetup: './global-setup.ts',
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8080',
    storageState: '.auth/admin.json',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
})
