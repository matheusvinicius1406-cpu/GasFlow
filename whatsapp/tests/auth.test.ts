/**
 * SEC-02 — Matriz de autenticação do gateway (chave configurada).
 *
 * As constantes API_KEY/ALLOW_INSECURE_AUTH de auth.ts são lidas no load do
 * módulo: o ENV precisa estar definido ANTES do import dinâmico (ESM).
 */
process.env.MARCOS_GAS_API_KEY = 'sec02-auth-matrix-key-0123456789';
delete process.env.ALLOW_INSECURE_AUTH;
process.env.ENVIRONMENT = 'production';

import assert from 'node:assert/strict';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import type { Request } from 'express';
import { after, describe, it } from 'node:test';

const { requireAuth, isAuthEnabled, hasValidApiKey } = await import('../src/auth.js');
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

async function get(path: string, authHeader?: string): Promise<Response> {
  const headers: Record<string, string> = {};
  if (authHeader !== undefined) headers.authorization = authHeader;
  return fetch(base + path, { headers });
}

describe('SEC-02 requireAuth — key configurada (fail-closed)', () => {
  it('sem header Authorization → 401', async () => {
    const res = await get('/protected');
    assert.equal(res.status, 401);
    const body = (await res.json()) as { error?: string };
    assert.match(String(body.error), /Token/);
  });

  it('Bearer com chave errada → 401', async () => {
    const res = await get('/protected', 'Bearer totally-wrong-key');
    assert.equal(res.status, 401);
  });

  it('Bearer com comprimento diferente → 401 (branch de length)', async () => {
    const res = await get('/protected', 'Bearer short');
    assert.equal(res.status, 401);
  });

  it('scheme ≠ Bearer → 401', async () => {
    const res = await get('/protected', `Basic ${KEY}`);
    assert.equal(res.status, 401);
  });

  it('chave correta → 200 (timing-safe)', async () => {
    const res = await get('/protected', `Bearer ${KEY}`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { ok: true });
  });

  it('isAuthEnabled() === true quando há chave', () => {
    assert.equal(isAuthEnabled(), true);
  });

  it('hasValidApiKey não termina a resposta (true/false conforme Bearer)', () => {
    const without = { headers: {} } as Request;
    const withKey = { headers: { authorization: `Bearer ${KEY}` } } as Request;
    const withWrong = { headers: { authorization: 'Bearer nope' } } as Request;
    assert.equal(hasValidApiKey(without), false);
    assert.equal(hasValidApiKey(withKey), true);
    assert.equal(hasValidApiKey(withWrong), false);
  });
});
