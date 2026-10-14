/**
 * Testes HTTP de ponta a ponta da API (app factory real, sem subir o
 * processo nem tocar no provider do WhatsApp). Cobre validação de entrada,
 * JSON malformado, 404 JSON e o fluxo principal de listas/clientes/campanhas.
 */
process.env.DATA_DIR = 'data/test-' + Date.now() + '-' + process.pid + '-' + Math.random().toString(36).slice(2, 8);

import assert from 'node:assert/strict';
import fs from 'node:fs';
import type { Server } from 'node:http';
import { after, before, test } from 'node:test';
import { createApp } from '../src/app';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { closeDb, db, insertContact, promoteContactToCustomer } = require('../src/db');

let server: Server;
let base = '';

async function api(method: string, path: string, body?: unknown, raw?: string) {
  const res = await fetch(base + path, {
    method,
    headers: raw !== undefined ? { 'content-type': 'application/json' } : { 'content-type': 'application/json' },
    body: raw !== undefined ? raw : body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json: unknown = null;
  try {
    json = JSON.parse(text);
  } catch {
    // resposta não-JSON (ex.: HTML) fica em `text`
  }
  return { status: res.status, json, text, headers: res.headers };
}

before(async () => {
  const app = createApp();
  await new Promise<void>((resolve) => {
    server = app.listen(0, '127.0.0.1', () => resolve());
  });
  const address = server.address();
  if (address === null || typeof address === 'string') throw new Error('Falha ao subir servidor de teste');
  base = `http://127.0.0.1:${address.port}`;
});

after(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
  try {
    closeDb();
  } catch {
    // ignore
  }
  try {
    fs.rmSync(process.env.DATA_DIR as string, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  } catch {
    // ignore
  }
});

// ---------------------------------------------------------------------------
// Health / status
// ---------------------------------------------------------------------------

test('GET /api/health é público e retorna ok', async () => {
  const res = await api('GET', '/api/health');
  assert.equal(res.status, 200);
  assert.equal((res.json as { ok: boolean }).ok, true);
  assert.ok((res.json as { whatsapp: { state: string } }).whatsapp.state);
});

test('GET /api/whatsapp/status é público', async () => {
  const res = await api('GET', '/api/whatsapp/status');
  assert.equal(res.status, 200);
  assert.ok('state' in (res.json as object));
});

// ---------------------------------------------------------------------------
// Validação de entrada e erros estruturados
// ---------------------------------------------------------------------------

test('JSON malformado retorna 400 (não 500)', async () => {
  const res = await api('POST', '/api/lists', undefined, '{"name": ');
  assert.equal(res.status, 400);
  assert.match(String((res.json as { error?: string }).error), /JSON/i);
});

test('rota desconhecida em /api retorna 404 JSON (não HTML)', async () => {
  const res = await api('GET', '/api/rota-que-nao-existe');
  assert.equal(res.status, 404);
  assert.equal((res.json as { error?: string }).error, 'Rota não encontrada.');
  assert.match(String(res.headers.get('content-type')), /application\/json/);
});

test('POST /api/lists sem name retorna 400', async () => {
  const res = await api('POST', '/api/lists', { description: 'x' });
  assert.equal(res.status, 400);
  assert.match(String((res.json as { error?: string }).error), /name/);
});

test('promote com status inválido retorna 400 (não 500)', async () => {
  const jid = `promote-invalido-${Date.now()}@c.us`;
  insertContact({ phone: '5511911111111', jid, name: 'Inválido', pushName: null, businessName: null, isBusiness: 0, isGroup: 0 });
  const contact = db.prepare('SELECT id FROM contacts WHERE jid = ?').get(jid) as { id: number };

  const res = await api('POST', `/api/customers/${contact.id}/promote`, { status: 'HACKED' });
  assert.equal(res.status, 400);
  assert.match(String((res.json as { error?: string }).error), /Status inválido/);
});

// ---------------------------------------------------------------------------
// Ciclo de vida de listas
// ---------------------------------------------------------------------------

test('criar, listar, renomear e remover lista', async () => {
  const created = await api('POST', '/api/lists', { name: `HTTP Lista ${Date.now()}`, description: 'via teste' });
  assert.equal(created.status, 201);
  const listId = (created.json as { id: number }).id;

  const dup = await api('POST', '/api/lists', { name: (created.json as { name: string }).name });
  assert.equal(dup.status, 409, 'nome duplicado deve dar 409');

  const listed = await api('GET', '/api/lists');
  assert.equal(listed.status, 200);
  assert.ok((listed.json as { lists: unknown[] }).lists.length >= 1);

  const renamed = await api('PUT', `/api/lists/${listId}`, { description: 'renomeada' });
  assert.equal(renamed.status, 200);
  assert.equal((renamed.json as { description: string }).description, 'renomeada');

  const missing = await api('PUT', '/api/lists/999999', { description: 'x' });
  assert.equal(missing.status, 404);

  const del = await api('DELETE', `/api/lists/${listId}`);
  assert.equal(del.status, 204);
  const delAgain = await api('DELETE', `/api/lists/${listId}`);
  assert.equal(delAgain.status, 404);
});

// ---------------------------------------------------------------------------
// Fluxo de clientes e campanha (sem envio real: worker não é iniciado)
// ---------------------------------------------------------------------------

test('fluxo completo: contato -> customer -> lista -> campanha -> pause/cancel', async () => {
  const stamp = Date.now();
  const jid = `fluxo-${stamp}@c.us`;
  insertContact({ phone: '5511922222222', jid, name: 'Fluxo Teste', pushName: null, businessName: null, isBusiness: 0, isGroup: 0 });
  const contact = db.prepare('SELECT id FROM contacts WHERE jid = ?').get(jid) as { id: number };

  const promoted = await api('POST', `/api/customers/${contact.id}/promote`, { status: 'CUSTOMER' });
  assert.equal(promoted.status, 201);
  const customerId = (promoted.json as { id: number }).id;

  const optOut = await api('POST', `/api/customers/${customerId}/opt-out`, { source: 'http-test' });
  assert.equal(optOut.status, 200);
  assert.equal((optOut.json as { marketingStatus: string }).marketingStatus, 'OPTED_OUT');

  const list = await api('POST', '/api/lists', { name: `Fluxo Lista ${stamp}` });
  assert.equal(list.status, 201);
  const listId = (list.json as { id: number }).id;

  const add = await api('POST', `/api/lists/${listId}/customers/${customerId}`);
  assert.equal(add.status, 201);

  const listCustomers = await api('GET', `/api/lists/${listId}/customers`);
  assert.equal(listCustomers.status, 200);
  assert.equal((listCustomers.json as { total: number }).total, 1);

  const campaign = await api('POST', '/api/campaigns', { name: `Fluxo Camp ${stamp}`, message: 'Olá!', listId });
  assert.equal(campaign.status, 201);
  const campaignId = (campaign.json as { id: number }).id;

  const preview = await api('POST', `/api/campaigns/${campaignId}/preview`);
  assert.equal(preview.status, 200);
  assert.equal((preview.json as { eligible: number }).eligible, 0, 'opt-out não é elegível');
  assert.equal((preview.json as { optedOut: number }).optedOut, 1);

  const start = await api('POST', `/api/campaigns/${campaignId}/start`);
  assert.equal(start.status, 200);
  assert.equal((start.json as { campaign: { status: string } }).campaign.status, 'RUNNING');

  const startedAt = (start.json as { campaign: { started_at: string | null } }).campaign.started_at;
  assert.ok(startedAt, 'started_at definido no primeiro start');

  const pause = await api('POST', `/api/campaigns/${campaignId}/pause`);
  assert.equal(pause.status, 200);

  const resume = await api('POST', `/api/campaigns/${campaignId}/start`);
  assert.equal(resume.status, 200);
  assert.equal(
    (resume.json as { campaign: { started_at: string | null } }).campaign.started_at,
    startedAt,
    'retomar não zera started_at',
  );

  const cancel = await api('POST', `/api/campaigns/${campaignId}/cancel`);
  assert.equal(cancel.status, 200);
  assert.equal((cancel.json as { campaign: { status: string } }).campaign.status, 'CANCELLED');

  const cancelAgain = await api('POST', `/api/campaigns/${campaignId}/cancel`);
  assert.equal(cancelAgain.status, 409, 'campanha já cancelada não cancela de novo');

  const results = await api('GET', `/api/campaigns/${campaignId}/results`);
  assert.equal(results.status, 200);
  assert.ok((results.json as { results: { cancelled: number } }).results.cancelled >= 1);
});

test('DELETE inexistente e GET de contato inexistente retornam 404', async () => {
  assert.equal((await api('GET', '/api/contacts/99999999')).status, 404);
  assert.equal((await api('GET', '/api/customers/99999999')).status, 404);
  assert.equal((await api('GET', '/api/campaigns/99999999')).status, 404);
  assert.equal((await api('POST', '/api/customers/99999999/promote')).status, 404);
});

test('promote é idempotente via HTTP', async () => {
  const jid = `promote-http-${Date.now()}@c.us`;
  insertContact({ phone: '5511933333333', jid, name: 'Idem', pushName: null, businessName: null, isBusiness: 0, isGroup: 0 });
  const contact = db.prepare('SELECT id FROM contacts WHERE jid = ?').get(jid) as { id: number };

  const first = await api('POST', `/api/customers/${contact.id}/promote`, { status: 'PROSPECT' });
  const second = await api('POST', `/api/customers/${contact.id}/promote`, { status: 'CUSTOMER' });
  assert.equal(first.status, 201);
  assert.equal(second.status, 201);
  assert.equal((first.json as { id: number }).id, (second.json as { id: number }).id);

  // Status original preservado (idempotente não sobrescreve).
  const customer = promoteContactToCustomer(contact.id);
  const row = db.prepare('SELECT customer_status FROM customers WHERE id = ?').get(customer) as { customer_status: string };
  assert.equal(row.customer_status, 'PROSPECT');
});
