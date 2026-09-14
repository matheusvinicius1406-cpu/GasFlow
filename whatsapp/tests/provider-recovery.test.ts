/**
 * Provider recovery tests — incidente 2026-09-06 (loop 408/QR) e paths do
 * prompt de correção (A: logged_out 401, B: 428 sessão Signal, C: 515).
 *
 * Estratégia: AccountInstance REAL + engine FALSO (sem Baileys/rede) —
 * handleEngineEvent é público justamente para permitir isso.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { AccountInstance } from '../src/provider/provider-manager';
import type { BaileysEngine } from '../src/provider/baileys-engine';

const settle = (ms = 30): Promise<void> => new Promise((r) => setTimeout(r, ms));

class FakeEngine {
  logoutCalls = 0;
  disconnectCalls = 0;
  clearCalls = 0;
  behavior: 'resolve' | 'hang' | 'reject' = 'resolve';

  logout(): Promise<void> {
    this.logoutCalls += 1;
    if (this.behavior === 'hang') return new Promise(() => undefined);
    if (this.behavior === 'reject') return Promise.reject(new Error('socket morto'));
    return Promise.resolve();
  }

  async disconnect(): Promise<void> {
    this.disconnectCalls += 1;
  }

  async clearSignalSession(): Promise<void> {
    this.clearCalls += 1;
  }
}

function makeAccount(engine: FakeEngine): {
  account: AccountInstance;
  reinitCalls: { count: number };
  sawBaileysAtReinit: Array<unknown>;
} {
  const account = new AccountInstance({ id: 'primary', name: 'Teste', sessionDir: 'unused' });
  const reinitCalls = { count: 0 };
  const sawBaileysAtReinit: Array<unknown> = [];
  // Intercepta o re-init (evita Baileys real). Shadow de método na instância.
  // Modelo fiel da produção: createAndInitializeClient() SEMPRE cria um novo
  // engine — então o shadow reinstala o fake. O valor de this.baileys no
  // INSTANTE do re-init é o observável do ciclo (null = pós-logout/wipe).
  (account as unknown as { createAndInitializeClient: () => void }).createAndInitializeClient = () => {
    sawBaileysAtReinit.push((account as unknown as { baileys: unknown }).baileys);
    reinitCalls.count += 1;
    (account as unknown as { baileys: BaileysEngine | null }).baileys = engine as unknown as BaileysEngine;
  };
  (account as unknown as { baileys: BaileysEngine | null }).baileys = engine as unknown as BaileysEngine;
  return { account, reinitCalls, sawBaileysAtReinit };
}

describe('Caminho A — logged_out (401): wipe creds + re-init', () => {
  it('logout 1×, engine nulo no re-init (wipe) e re-init depois', async () => {
    const engine = new FakeEngine();
    const { account, reinitCalls, sawBaileysAtReinit } = makeAccount(engine);

    account.handleEngineEvent('logged_out');
    await settle();

    assert.equal(engine.logoutCalls, 1);
    assert.equal(sawBaileysAtReinit[0], null); // baileys null ENTRE logout e re-init
    assert.equal(reinitCalls.count, 1);
  });

  it('re-entrância: segundo logged_out durante recovery não roda 2º ciclo', async () => {
    const engine = new FakeEngine();
    engine.behavior = 'hang'; // recovery pendente
    const { account, reinitCalls } = makeAccount(engine);

    account.handleEngineEvent('logged_out');
    await settle();
    account.handleEngineEvent('logged_out'); // rajada — deve ser suprimido
    await settle();

    assert.equal(engine.logoutCalls, 1);
    assert.equal(reinitCalls.count, 0);
  });

  it('logout travado: timeout dispara e recovery conclui com re-init', async () => {
    const engine = new FakeEngine();
    engine.behavior = 'hang';
    const { account, reinitCalls, sawBaileysAtReinit } = makeAccount(engine);
    (account as unknown as { logoutTimeoutMs: number }).logoutTimeoutMs = 50;

    account.handleEngineEvent('logged_out');
    await settle(150); // > timeout de 50ms

    assert.equal(engine.logoutCalls, 1);
    assert.equal(sawBaileysAtReinit[0], null);
    assert.equal(reinitCalls.count, 1);
  });

  it('logout que rejeita: erro logado, recovery segue com re-init', async () => {
    const engine = new FakeEngine();
    engine.behavior = 'reject';
    const { account, reinitCalls, sawBaileysAtReinit } = makeAccount(engine);

    account.handleEngineEvent('logged_out');
    await settle();

    assert.equal(engine.logoutCalls, 1);
    assert.equal(sawBaileysAtReinit[0], null);
    assert.equal(reinitCalls.count, 1);
  });
});

const internalsOf = (account: AccountInstance) =>
  account as unknown as { reconnectTimer: NodeJS.Timeout | null; clearReconnectTimer: () => void };

describe('Caminho B — 428/440: limpa sessão Signal, preserva creds', () => {
  it('428 → clearSignalSession + backoff agendado, SEM logout e SEM tocar creds', async () => {
    const engine = new FakeEngine();
    const { account, reinitCalls } = makeAccount(engine);

    account.handleEngineEvent('disconnected', '428');
    await settle();

    assert.equal(engine.clearCalls, 1);
    assert.equal(engine.logoutCalls, 0);
    assert.notEqual(internalsOf(account).reconnectTimer, null); // backoff existente
    assert.equal(reinitCalls.count, 0); // re-init só quando o timer disparar
    internalsOf(account).clearReconnectTimer();
  });

  it('4 falhas 428 seguidas → escala para wipe completo na 4ª', async () => {
    const engine = new FakeEngine();
    const { account, reinitCalls, sawBaileysAtReinit } = makeAccount(engine);

    for (let i = 0; i < 4; i += 1) {
      account.handleEngineEvent('disconnected', '428');
      await settle();
      internalsOf(account).clearReconnectTimer(); // não esperar o backoff real
    }

    assert.equal(engine.clearCalls, 3); // tentativas 1–3
    assert.equal(engine.logoutCalls, 1); // escalada na 4ª
    // Único re-init imediato é o pós-wipe (da escalada), partindo de null;
    // os re-inits dos ciclos 1–3 ficam pendentes no timer de backoff (cancelado).
    assert.deepEqual(sawBaileysAtReinit, [null]);
    assert.equal(reinitCalls.count, 1);
  });
});

describe('Caminho C — 515 restart required', () => {
  it('primeiro 515 → reconexão simples (sem limpeza); repetido → caminho B', async () => {
    const engine = new FakeEngine();
    const { account, reinitCalls } = makeAccount(engine);

    account.handleEngineEvent('disconnected', '515');
    await settle();
    assert.equal(engine.clearCalls, 0);
    assert.notEqual(internalsOf(account).reconnectTimer, null); // só agendou backoff
    assert.equal(reinitCalls.count, 0);

    account.handleEngineEvent('disconnected', '515');
    await settle();
    assert.equal(engine.clearCalls, 1); // 515 persistente → caminho B
    assert.equal(engine.logoutCalls, 0);

    (account as unknown as { clearReconnectTimer: () => void }).clearReconnectTimer();
  });
});

describe('Telemetria — transições e contador por motivo', () => {
  it('disconnectsByReason conta cada motivo', async () => {
    const engine = new FakeEngine();
    const { account } = makeAccount(engine);
    const stats = () => (account as unknown as { getDisconnectStats: () => Record<string, number> }).getDisconnectStats();

    account.handleEngineEvent('disconnected', '408');
    account.handleEngineEvent('disconnected', '408');
    account.handleEngineEvent('logged_out');
    await settle();

    assert.equal(stats()['408'], 2);
    assert.equal(stats()['logged_out_401'], 1);
  });
});
