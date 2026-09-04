import { request as pwRequest } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

/**
 * Logs in once via the real API and persists the session to storageState.
 *
 * Every spec reuses this state — the app has a login rate limiter
 * (5 attempts/5min per worker) and a suite that logs in per test would
 * hit 429s and flake.
 */
const BASE_URL = process.env.BASE_URL || 'http://localhost:8080'
const ADMIN_USER = 'admin'
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin123'
const STATE_DIR = join(__dirname, '.auth')
const STATE_PATH = join(STATE_DIR, 'admin.json')

export default async function globalSetup() {
  const ctx = await pwRequest.newContext({ baseURL: BASE_URL })
  const res = await ctx.post('/api/auth/login', {
    data: { username: ADMIN_USER, password: ADMIN_PASSWORD },
  })
  if (res.status() !== 200) {
    throw new Error(
      `global-setup: login falhou (${res.status()}). Stack E2E está no ar? ` +
        `Rode: docker compose -f docker-compose.e2e.yml up -d --build`,
    )
  }
  const body = await res.json()
  await ctx.dispose()

  mkdirSync(STATE_DIR, { recursive: true })
  writeFileSync(
    STATE_PATH,
    JSON.stringify({
      cookies: [],
      origins: [
        {
          origin: BASE_URL,
          localStorage: [{ name: 'gasflow_token', value: body.token }],
        },
      ],
    }),
    'utf-8',
  )
}
