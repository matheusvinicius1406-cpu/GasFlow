/**
 * SEC-02 — Modo inseguro de DEV documentado e contido.
 *
 * Sem chave + ALLOW_INSECURE_AUTH=true fora de produção = bypass aberto
 * (contrato atual, preservado de propósito para desenvolvimento local).
 * O teste documenta o comportamento para que qualquer mudança futura de
 * fail-closed apareça como quebra aqui.
 *
 * ENV definido ANTES do import dinâmico de auth.ts (constantes no load).
 */
delete process.env.MARCOS_GAS_API_KEY;
process.env.ALLOW_INSECURE_AUTH = 'true';
process.env.ENVIRONMENT = 'development';

import assert from 'node:assert/strict';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import type { Request } from 'express';
import { after, describe, it } from 'node:test';

const { requireAuth, isAuthEnabled, hasValidApiKey } = await import('../src/auth.js');
const express = (await import('express')).default;

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

describe('SEC-02 bypass de dev (sem chave, fora de produção)', () => {
  it('sem header → liberado (modo dev)', async () => {
    const res = await fetch(`${base}/protected`);
    assert.equal(res.status, 200);
  });

  it('isAuthEnabled() === false (nenhuma chave ativa)', () => {
    assert.equal(isAuthEnabled(), false);
  });

  it('hasValidApiKey reflete o bypass dev', () => {
    const without = { headers: {} } as Request;
    assert.equal(hasValidApiKey(without), true);
  });
});
