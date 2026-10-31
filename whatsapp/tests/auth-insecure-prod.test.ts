/**
 * SEC-02 — ALLOW_INSECURE_AUTH=true NUNCA enfraquece ENVIRONMENT=production.
 *
 * O flag existe para dev; em produção ele é ignorado no load do módulo e a
 * exigência de Bearer permanece. Este teste fecha esta regressão
 * (flag vazando para prod).
 *
 * ENV definido ANTES do import dinâmico de auth.ts (constantes no load).
 */
process.env.MARCOS_GAS_API_KEY = 'sec02-prod-bypass-key-0123456789';
process.env.ALLOW_INSECURE_AUTH = 'true';
process.env.ENVIRONMENT = 'production';

import assert from 'node:assert/strict';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { after, describe, it } from 'node:test';

const { requireAuth } = await import('../src/auth.js');
const express = (await import('express')).default;

const KEY = process.env.MARCOS_GAS_API_KEY as string;

const app = express();
app.get('/protected', requireAuth, (_req, res) => {
  res.json({ ok: true });
});

const server: Server = await new Promise((resolve) => {
  const s = app.listen(0, () => resolve(s));
});
const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;

after(() => {
  server.close();
});

describe('SEC-02 produção ignora ALLOW_INSECURE_AUTH', () => {
  it('produção + flag insegura + sem header → 401', async () => {
    const res = await fetch(`${base}/protected`);
    assert.equal(res.status, 401);
  });

  it('produção + flag insegura + chave correta → 200', async () => {
    const res = await fetch(`${base}/protected`, { headers: { authorization: `Bearer ${KEY}` } });
    assert.equal(res.status, 200);
  });
});
