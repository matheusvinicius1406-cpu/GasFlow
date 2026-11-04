/**
 * SEC-02 — Matriz de autorização das rotas do router da API.
 *
 * Prova:
 *  1. NEGATIVA  — sem Authorization, TODA rota de dados (incl. as 9 que
 *     estavam expostas) responde 401; chave errada também.
 *  2. POSITIVA  — com chave válida o handler é alcançado (404/409/200
 *     conforme o estado), nunca 401.
 *
 * ENV/DATA_DIR definidos ANTES dos imports dinâmicos (ESM): DATA_DIR
 * temporário isola o SQLite; a chave é lida no load de auth.ts.
 */
process.env.MARCOS_GAS_API_KEY = 'sec02-routes-key-0123456789abcdef';
delete process.env.ALLOW_INSECURE_AUTH;
process.env.ENVIRONMENT = 'production';
process.env.DATA_DIR =
  'data/test-routes-auth-' + Date.now() + '-' + process.pid + '-' + Math.random().toString(36).slice(2, 8);

import assert from 'node:assert/strict';
import fs from 'node:fs';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { after, describe, it } from 'node:test';

const express = (await import('express')).default;
const { router } = await import('../src/routes.js');

const KEY = process.env.MARCOS_GAS_API_KEY as string;

const app = express();
app.use(express.json({ limit: '1mb' }));
app.use('/api', router);

// Alias raiz /send (server.ts) — espelha o wiring do servidor para provar
// que a rota de compatibilidade do backend herda requireAuth do router.
app.post('/send', express.json({ limit: '1mb' }), (req, res, next) => {
  req.url = `/whatsapp/accounts/${encodeURIComponent(String((req.body as { accountId?: string } | undefined)?.accountId ?? 'primary'))}/messages`;
  (req as unknown as { body: unknown }).body = {
    recipient: (req.body as { recipient?: string } | undefined)?.recipient,
    message: (req.body as { text?: string } | undefined)?.text,
    idempotency_key: (req.body as { idempotencyKey?: string } | undefined)?.idempotencyKey,
  };
  router(req, res, next);
});

const server: Server = await new Promise((resolve) => {
  const s = app.listen(0, () => resolve(s));
});
const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;

after(async () => {
  server.close();
  try {
    const { closeDb } = await import('../src/db.js');
    closeDb();
  } catch {
    // já fechado / não aberto
  }
  try {
    fs.rmSync(process.env.DATA_DIR as string, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  } catch {
    // melhor esforço
  }
});

async function call(method: string, path: string, authHeader?: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  if (authHeader !== undefined) headers.authorization = authHeader;
  if (body !== undefined) headers['content-type'] = 'application/json';
  return fetch(base + path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

// As 9 rotas que estavam SEM requireAuth (foco do SEC-02A) + amostras das
// já protegidas para garantir que a cobertura não regrediu.
const ROTAS_PROTEGIDAS: Array<[string, string]> = [
  // ── corrigidas neste elemento ──
  ['GET', '/api/whatsapp/health'],
  ['GET', '/api/contacts/1'],
  ['GET', '/api/customers/1'],
  ['GET', '/api/lists/1'],
  ['GET', '/api/lists/1/contacts'],
  ['GET', '/api/lists/1/customers'],
  ['GET', '/api/campaigns/1'],
  ['GET', '/api/campaigns/1/recipients'],
  ['GET', '/api/campaigns/1/results'],
  // ── já protegidas (regressão) ──
  ['GET', '/api/whatsapp/accounts'],
  ['GET', '/api/whatsapp/accounts/primary/qr'],
  ['POST', '/api/whatsapp/start'],
  ['GET', '/api/campaigns'],
  ['POST', '/api/campaigns'],
  ['DELETE', '/api/lists/1'],
  ['PUT', '/api/customers/1/status'],
  ['POST', '/api/whatsapp/accounts/primary/messages'],
];

describe('SEC-02 rotas — sem API key → 401 (prova negativa)', () => {
  for (const [method, path] of ROTAS_PROTEGIDAS) {
    it(`${method} ${path} → 401 sem header`, async () => {
      const res = await call(method, path, undefined, method === 'POST' || method === 'PUT' ? {} : undefined);
      assert.equal(res.status, 401, `${method} ${path} expôs ${res.status} sem auth`);
    });
  }

  it('chave errada → 401 em rota que estava exposta', async () => {
    const res = await call('GET', '/api/lists/1', 'Bearer wrong-key');
    assert.equal(res.status, 401);
  });
});

describe('SEC-02 rotas — com chave válida → handler alcançado', () => {
  it('GET /api/whatsapp/accounts → 200 com primary e secondary', async () => {
    const res = await call('GET', '/api/whatsapp/accounts', `Bearer ${KEY}`);
    assert.equal(res.status, 200);
    const body = (await res.json()) as { accounts: Array<{ id: string }>; total: number };
    const ids = new Set(body.accounts.map((a) => a.id));
    assert.ok(ids.has('primary'));
    assert.ok(ids.has('secondary'));
    assert.equal(body.total, body.accounts.length);
  });

  it('GET /api/whatsapp/accounts/:id inexistente → 404 (conta inválida rejeitada)', async () => {
    const res = await call('GET', '/api/whatsapp/accounts/nao-existe', `Bearer ${KEY}`);
    assert.equal(res.status, 404);
  });

  it('GET /api/contacts/:id inexistente → 404 (handler executou, não-auth)', async () => {
    const res = await call('GET', '/api/contacts/999999999', `Bearer ${KEY}`);
    assert.equal(res.status, 404);
  });

  it('GET /api/lists/:id → 404 sem dados (handler executou)', async () => {
    const res = await call('GET', '/api/lists/999999999', `Bearer ${KEY}`);
    assert.equal(res.status, 404);
  });

  it('GET /api/campaigns → 200 (lista vazia)', async () => {
    const res = await call('GET', '/api/campaigns', `Bearer ${KEY}`);
    assert.equal(res.status, 200);
  });

  it('POST /messages conta desconectada → 409 (auth passou, checou estado)', async () => {
    const res = await call('POST', '/api/whatsapp/accounts/primary/messages', `Bearer ${KEY}`, {
      recipient: '5511999999999',
      message: 'oi',
    });
    assert.equal(res.status, 409);
    const body = (await res.json()) as { error?: string };
    assert.equal(body.error, 'ACCOUNT_NOT_CONNECTED');
  });

  it('GET /api/whatsapp/health → 503 healthy:false (conta nunca conectada no teste)', async () => {
    const res = await call('GET', '/api/whatsapp/health', `Bearer ${KEY}`);
    assert.notEqual(res.status, 401);
    const body = (await res.json()) as { healthy?: boolean };
    assert.equal(body.healthy, false);
  });
});

describe('SEC-02 alias /send (compat backend) — mesmo tratamento do router', () => {
  it('sem header → 401 (alias herda requireAuth)', async () => {
    const res = await call('POST', '/send', undefined, { recipient: '5511999999999', text: 'oi' });
    assert.equal(res.status, 401);
  });

  it('chave errada → 401', async () => {
    const res = await call('POST', '/send', 'Bearer wrong', { recipient: '5511999999999', text: 'oi' });
    assert.equal(res.status, 401);
  });

  it('chave válida → handler alcançado (409 conta desconectada, nunca 401)', async () => {
    const res = await call('POST', '/send', `Bearer ${KEY}`, { recipient: '5511999999999', text: 'oi' });
    assert.equal(res.status, 409);
    const body = (await res.json()) as { error?: string };
    assert.equal(body.error, 'ACCOUNT_NOT_CONNECTED');
  });
});
