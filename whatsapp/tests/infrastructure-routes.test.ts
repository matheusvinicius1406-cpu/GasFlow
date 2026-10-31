/**
 * SEC-02 — Rotas de infraestrutura (health/ready/connect/metrics).
 *
 * Política verificada:
 *  - /api/health  pública mínima {ok,uptime}; contas/memória SÓ com Bearer
 *    (contrato do health_check do adapter do backend preservado).
 *  - /api/ready   público sem vazar ids de contas.
 *  - /connect     HTML estático público.
 *  - /metrics     fail-closed por padrão; aberto só com METRICS_PUBLIC=true.
 *
 * ENV definido ANTES dos imports dinâmicos (ESM).
 */
process.env.MARCOS_GAS_API_KEY = 'sec02-infra-key-0123456789abcdef';
delete process.env.ALLOW_INSECURE_AUTH;
delete process.env.METRICS_PUBLIC;
process.env.ENVIRONMENT = 'production';
process.env.DATA_DIR =
  'data/test-infra-' + Date.now() + '-' + process.pid + '-' + Math.random().toString(36).slice(2, 8);

import assert from 'node:assert/strict';
import fs from 'node:fs';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { after, describe, it } from 'node:test';

const express = (await import('express')).default;
const { registerInfrastructureRoutes } = await import('../src/infrastructure-routes.js');

const KEY = process.env.MARCOS_GAS_API_KEY as string;
const startedAt = Date.now() - 5_000;

const app = express();
registerInfrastructureRoutes(app, startedAt);

const server: Server = await new Promise((resolve) => {
  const s = app.listen(0, () => resolve(s));
});
const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;

after(() => {
  server.close();
  try {
    fs.rmSync(process.env.DATA_DIR as string, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  } catch {
    // melhor esforço
  }
});

async function get(path: string, authHeader?: string): Promise<Response> {
  const headers: Record<string, string> = {};
  if (authHeader !== undefined) headers.authorization = authHeader;
  return fetch(base + path, { headers });
}

describe('SEC-02 /api/health — público mínimo, detalhe autenticado', () => {
  it('sem Bearer → corpo mínimo (sem contas, sem memória)', async () => {
    const res = await get('/api/health');
    assert.equal(res.status, 200);
    const body = (await res.json()) as Record<string, unknown>;
    assert.equal(body.ok, true);
    assert.equal(typeof body.uptimeSeconds, 'number');
    assert.ok(!('whatsapp' in body), 'vazou whatsapp/health sem auth');
    assert.ok(!('memory' in body), 'vazou memória sem auth');
  });

  it('com Bearer → corpo completo (contrato do adapter do backend)', async () => {
    const res = await get('/api/health', `Bearer ${KEY}`);
    assert.equal(res.status, 200);
    const body = (await res.json()) as {
      whatsapp?: { accounts: Array<{ id: string }>; total: number };
      memory?: { rssMb: number };
    };
    assert.ok(body.whatsapp?.accounts, 'contrato whatsapp.accounts ausente com auth');
    const ids = new Set(body.whatsapp.accounts.map((a) => a.id));
    assert.ok(ids.has('primary'));
    assert.ok(ids.has('secondary'));
    assert.ok(body.memory, 'memória ausente com auth');
  });

  it('Bearer errado → tratado como público (corpo mínimo)', async () => {
    const res = await get('/api/health', 'Bearer wrong');
    assert.equal(res.status, 200);
    const body = (await res.json()) as Record<string, unknown>;
    assert.ok(!('whatsapp' in body));
  });
});

describe('SEC-02 /api/ready — público sem vazar ids', () => {
  it('200 com {ready,total} e SEM array accounts', async () => {
    const res = await get('/api/ready');
    assert.equal(res.status, 200);
    const body = (await res.json()) as { ready: boolean; total: number; accounts?: unknown };
    assert.equal(body.ready, true);
    assert.ok(body.total >= 1);
    assert.ok(!('accounts' in body), 'vazou accountIds sem auth');
  });
});

describe('SEC-02 /connect — HTML estático público', () => {
  it('200 text/html', async () => {
    const res = await get('/connect');
    assert.equal(res.status, 200);
    assert.match(String(res.headers.get('content-type')), /text\/html/);
  });
});

describe('SEC-02 /metrics — fail-closed por padrão, igual ao backend', () => {
  it('sem METRICS_PUBLIC e sem Bearer → 401', async () => {
    const res = await get('/metrics');
    assert.equal(res.status, 401);
  });

  it('com Bearer inválido → 401', async () => {
    const res = await get('/metrics', 'Bearer wrong');
    assert.equal(res.status, 401);
  });

  it('com Bearer válido → 200 text/plain', async () => {
    const res = await get('/metrics', `Bearer ${KEY}`);
    assert.equal(res.status, 200);
    assert.match(String(res.headers.get('content-type')), /text\/plain/);
    assert.ok((await res.text()).length > 0);
  });

  it('METRICS_PUBLIC=true → 200 sem Bearer (dev/scraper)', async () => {
    process.env.METRICS_PUBLIC = 'true';
    try {
      const res = await get('/metrics');
      assert.equal(res.status, 200);
    } finally {
      delete process.env.METRICS_PUBLIC;
    }
  });

  it('METRICS_PUBLIC=false explícito → 401 (fail-closed mantido)', async () => {
    process.env.METRICS_PUBLIC = 'false';
    try {
      const res = await get('/metrics');
      assert.equal(res.status, 401);
    } finally {
      delete process.env.METRICS_PUBLIC;
    }
  });
});
