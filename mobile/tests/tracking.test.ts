/**
 * Testes do rastreamento F2.5 (módulos puros — sem RN, node --test).
 *
 * Cobrem: gate B2 (auto on/off + override manual + work-hours LGPD),
 * cadência (intervalo do /driver/me), roteamento de envio (lan → cloud →
 * fila offline) e o TrackingController (captura só quando deve).
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  evaluateGate,
  normalizeInterval,
  shouldSendNow,
  sendPosition,
  TrackingController,
  type GpsPosition,
  type TrackingDeps,
  type TrackingSnapshot,
} from "../src/logic/tracking.ts";
import { OfflineQueue, type QueueStorage, type QueueItem } from "../src/logic/offlineQueue.ts";

const WINDOW = { start: "06:00", end: "22:00" };
const IN_WINDOW = new Date("2026-09-17T10:00:00");
const OUT_OF_WINDOW = new Date("2026-09-17T23:00:00");

// ── Gate B2 ─────────────────────────────────────────────────

test("gate: sem rota não rastreia; rota em qualquer status de rota rastreia", () => {
  const base = { override: null, workWindow: WINDOW, now: IN_WINDOW };
  assert.equal(evaluateGate({ ...base, statuses: ["DELIVERED"] }).tracking, false);
  assert.equal(evaluateGate({ ...base, statuses: [] }).tracking, false);
  for (const s of ["ASSIGNED", "DISPATCHED", "EN_ROUTE"]) {
    const d = evaluateGate({ ...base, statuses: [s] });
    assert.equal(d.tracking, true, s);
    assert.equal(d.phase, "active");
  }
});

test("gate: override manual — off vence rota ativa; on antecipa sem rota", () => {
  const base = { workWindow: WINDOW, now: IN_WINDOW };
  const off = evaluateGate({ ...base, statuses: ["EN_ROUTE"], override: false });
  assert.equal(off.tracking, false);
  assert.equal(off.reason, "manual_off");
  const on = evaluateGate({ ...base, statuses: ["DELIVERED"], override: true });
  assert.equal(on.tracking, true);
});

test("gate: work-hours vence TUDO (fail-closed, LGPD) — nem override manual captura", () => {
  const base = { statuses: ["EN_ROUTE"], override: true, workWindow: WINDOW, now: OUT_OF_WINDOW };
  const d = evaluateGate(base);
  assert.equal(d.tracking, false);
  assert.equal(d.reason, "out_of_hours");
  // janela vazia e config ausente também bloqueiam
  assert.equal(evaluateGate({ statuses: ["EN_ROUTE"], override: null, workWindow: null, now: IN_WINDOW }).tracking, false);
  assert.equal(evaluateGate({ statuses: ["EN_ROUTE"], override: null, workWindow: { start: "08:00", end: "08:00" }, now: IN_WINDOW }).tracking, false);
});

test("gate: onRoute informado para o controller limpar override quando a rota acaba", () => {
  const base = { override: false, workWindow: WINDOW, now: IN_WINDOW };
  assert.equal(evaluateGate({ ...base, statuses: ["EN_ROUTE"] }).onRoute, true);
  assert.equal(evaluateGate({ ...base, statuses: ["DELIVERED"] }).onRoute, false);
});

// ── Cadência ────────────────────────────────────────────────

test("cadência: intervalo do /driver/me com piso de 15s e default 120s", () => {
  assert.equal(normalizeInterval(120), 120);
  assert.equal(normalizeInterval(5), 15);
  assert.equal(normalizeInterval(0), 15);
  assert.equal(normalizeInterval(-3), 15);
  assert.equal(normalizeInterval(Number.NaN), 120);
  assert.equal(normalizeInterval(undefined), 120);
});

test("cadência: envio só a cada intervalo; primeira posição sai na hora", () => {
  assert.equal(shouldSendNow(null, 1_000_000, 120), true);
  assert.equal(shouldSendNow(1_000_000, 1_000_000 + 119_999, 120), false);
  assert.equal(shouldSendNow(1_000_000, 1_000_000 + 120_000, 120), true);
  // intervalo mínimo vale para a cadência também
  assert.equal(shouldSendNow(1_000_000, 1_000_000 + 15_000, 5), true);
});

// ── Roteamento de envio ─────────────────────────────────────

const POS: GpsPosition = { latitude: -1.4558, longitude: -48.4902, speed: 30, accuracy: 10, timestamp: 1_000 };

test("envio: lan usa POST /api/v1/driver/location com JWT", async () => {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fetchFn = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return { ok: true, json: async () => ({ success: true }) } as Response;
  }) as typeof fetch;
  const via = await sendPosition(
    fetchFn,
    { connection: { mode: "lan", baseUrl: "http://dep:8000" }, token: "jwt", relayToken: "", driverId: "d1", tenantId: "default" },
    POS,
  );
  assert.equal(via, "lan");
  assert.equal(calls[0].url, "http://dep:8000/api/v1/driver/location");
  assert.equal((calls[0].init.headers as Record<string, string>).Authorization, "Bearer jwt");
  const body = JSON.parse(String(calls[0].init.body));
  assert.equal(body.latitude, -1.4558);
});

test("envio: cloud usa relay com X-Relay-Token e payload LocationPing", async () => {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fetchFn = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return { ok: true, json: async () => ({ accepted: 1 }) } as Response;
  }) as typeof fetch;
  const via = await sendPosition(
    fetchFn,
    {
      connection: { mode: "cloud", baseUrl: "https://relay.app" },
      token: "jwt",
      relayToken: "rt",
      driverId: "d1",
      tenantId: "default",
    },
    POS,
  );
  assert.equal(via, "cloud");
  assert.equal(calls[0].url, "https://relay.app/driver/location");
  assert.equal((calls[0].init.headers as Record<string, string>)["X-Relay-Token"], "rt");
  const body = JSON.parse(String(calls[0].init.body));
  assert.equal(body.driver_id, "d1");
  assert.equal(body.positions.length, 1);
  assert.equal(body.positions[0].lat, -1.4558);
  assert.equal(typeof body.positions[0].recorded_at, "string");
});

test("envio: sem canal devolve queued; sem credencial do canal também", async () => {
  const fetchFn = (async () => {
    throw new Error("não deveria chamar");
  }) as typeof fetch;
  assert.equal(
    await sendPosition(fetchFn, { connection: { mode: "offline", baseUrl: null }, token: "", relayToken: "", driverId: "d1", tenantId: "t" }, POS),
    "queued",
  );
  // lan sem token → não tem como autenticar → queued
  assert.equal(
    await sendPosition(fetchFn, { connection: { mode: "lan", baseUrl: "http://x" }, token: "", relayToken: "", driverId: "d1", tenantId: "t" }, POS),
    "queued",
  );
});

// ── TrackingController ──────────────────────────────────────

function memoryQueueStorage(): QueueStorage & { items: QueueItem[] } {
  const items: QueueItem[] = [];
  return {
    items,
    all: () => items.slice(),
    save: (item) => {
      const idx = items.findIndex((i) => i.client_action_id === item.client_action_id);
      if (idx >= 0) items[idx] = { ...item };
      else items.push({ ...item });
    },
  };
}

interface Harness {
  controller: TrackingController;
  setSnapshot: (patch: Partial<TrackingSnapshot>) => void;
  watchCalls: number;
  stopCalls: number;
  emitPosition: (p: GpsPosition) => void;
  queueStorage: QueueStorage & { items: QueueItem[] };
  now: () => number;
  setClock: (ms: number) => void;
}

function makeHarness(initial: Partial<TrackingSnapshot> = {}): Harness {
  let clock = 1_000_000;
  const watchCount = { calls: 0, stops: 0 };
  let onPosition: ((p: GpsPosition) => void) | null = null;
  const snap: TrackingSnapshot = {
    statuses: [],
    workWindow: WINDOW,
    intervalSeconds: 120,
    token: "jwt",
    relayToken: "rt",
    driverId: "d1",
    tenantId: "default",
    connection: { mode: "offline", baseUrl: null },
    ...initial,
  };
  const queue = new OfflineQueue(memoryQueueStorage());
  const deps: TrackingDeps = {
    fetchFn: (async () => {
      throw new Error("rede indisponível");
    }) as typeof fetch,
    now: () => clock,
    getSnapshot: () => ({ ...snap }),
    watch: (onPos) => {
      watchCount.calls += 1;
      onPosition = onPos;
      return () => {
        watchCount.stops += 1;
        onPosition = null;
      };
    },
    queue,
  };
  const controller = new TrackingController(deps);
  return {
    controller,
    setSnapshot: (patch) => Object.assign(snap, patch),
    get watchCalls() {
      return watchCount.calls;
    },
    get stopCalls() {
      return watchCount.stops;
    },
    emitPosition: (p) => onPosition?.(p),
    get queueStorage() {
      return queue.storage as QueueStorage & { items: QueueItem[] };
    },
    now: () => clock,
    setClock: (ms: number) => {
      clock = ms;
    },
  };
}

test("controller: sem rota não captura; rota ativa captura e enfileira offline", async () => {
  const h = makeHarness();
  await h.controller.tickOnce();
  assert.equal(h.watchCalls, 0);

  h.setSnapshot({ statuses: ["EN_ROUTE"] });
  await h.controller.tickOnce();
  assert.equal(h.watchCalls, 1);
  assert.equal(h.controller.getStatus().phase, "active");

  // posição chega, sem canal → vai para a fila (kind location)
  h.emitPosition({ latitude: -1.4558, longitude: -48.4902, timestamp: h.now() });
  await h.controller.tickOnce();
  assert.equal(h.controller.getStatus().lastSentAt !== null, true);
  const queued = h.queueStorage.items;
  assert.equal(queued.length, 1);
  assert.equal(queued[0].kind, "location");
  assert.equal(queued[0].payload.latitude, -1.4558);
});

test("controller: rota termina → captura para e override é limpo (próxima rota religa)", async () => {
  const h = makeHarness({ statuses: ["EN_ROUTE"] });
  await h.controller.tickOnce();
  assert.equal(h.watchCalls, 1);

  h.controller.setOverride(false); // "desligado por você"
  await h.controller.tickOnce();
  assert.equal(h.controller.getStatus().phase, "paused");
  assert.equal(h.controller.getStatus().reason, "manual_off");

  // rota termina com override manual pendente: watch para e override é limpo
  h.setSnapshot({ statuses: ["DELIVERED"] });
  await h.controller.tickOnce();
  assert.equal(h.stopCalls, 1);
  assert.equal(h.controller.getOverride(), null);
  // próximo ciclo já volta ao estado automático de espera
  await h.controller.tickOnce();
  assert.equal(h.controller.getStatus().phase, "waiting");
  assert.equal(h.stopCalls, 1, "watch não religa sem rota");
  assert.equal(h.controller.getOverride(), null);
});

test("controller: desligado manualmente não captura nada; fora da janela idem", async () => {
  const h = makeHarness({ statuses: ["EN_ROUTE"] });
  h.controller.setOverride(false);
  await h.controller.tickOnce();
  assert.equal(h.watchCalls, 0);

  h.controller.setOverride(null);
  h.setSnapshot({ workWindow: null });
  await h.controller.tickOnce();
  assert.equal(h.watchCalls, 0);
  assert.equal(h.controller.getStatus().reason, "out_of_hours");
});

test("controller: cadência de 120s — segunda posição antes do intervalo não reenvia", async () => {
  const h = makeHarness({ statuses: ["EN_ROUTE"] });
  await h.controller.tickOnce(); // liga o watch
  assert.equal(h.watchCalls, 1);

  h.emitPosition({ latitude: -1.4558, longitude: -48.4902, timestamp: h.now() });
  await h.controller.tickOnce(); // 1º envio (fila)
  assert.equal(h.queueStorage.items.length, 1);

  // posição nova imediatamente depois: < intervalo → throttle
  h.emitPosition({ latitude: -1.46, longitude: -48.49, timestamp: h.now() + 5_000 });
  await h.controller.tickOnce();
  assert.equal(h.queueStorage.items.length, 1, "throttle respeitado");

  // avança o relógio 121s: próximo tick envia de novo
  h.setClock(h.now() + 121_000);
  h.emitPosition({ latitude: -1.47, longitude: -48.5, timestamp: h.now() });
  await h.controller.tickOnce();
  assert.equal(h.queueStorage.items.length, 2);
});

test("controller: falha de rede LAN enfileira e registra o erro", async () => {
  const h = makeHarness({ statuses: ["EN_ROUTE"], connection: { mode: "lan", baseUrl: "http://dep:8000" } });
  await h.controller.tickOnce(); // liga o watch
  h.emitPosition({ latitude: -1.4558, longitude: -48.4902 });
  await h.controller.tickOnce(); // tenta enviar → lan falha → enfileira
  const st = h.controller.getStatus();
  assert.equal(st.lastError !== null, true, "erro registrado");
  assert.equal(h.queueStorage.items.length, 1, "posição na fila para replay");
});
