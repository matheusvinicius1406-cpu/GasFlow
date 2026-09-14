/**
 * Testes de lógica do App do Entregador (módulos puros — sem RN).
 * Rodam com `node --test tests/` (Node ≥22, type stripping nativo).
 *
 * Cobrem: work-hours LGPD (prompt 5.3/8), fila offline com idempotência
 * e backoff (prompt 5.4) e fallback LAN→nuvem→offline (prompt 2.2).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { isWithinWorkHours, parseWindow, DEFAULT_WORK_WINDOW } from "../src/logic/workHours.ts";
import { OfflineQueue, type QueueItem, type QueueStorage } from "../src/logic/offlineQueue.ts";
import { resolveConnection } from "../src/logic/connection.ts";

// ── workHours (LGPD) ─────────────────────────────────────────

test("workHours: coleta dentro da janela, bloqueia fora", () => {
  const window = { start: "06:00", end: "20:00" };
  assert.equal(isWithinWorkHours(new Date("2026-09-14T10:00:00"), window), true);
  assert.equal(isWithinWorkHours(new Date("2026-09-14T21:00:00"), window), false);
  // borda: 06:00 inclusive, 20:00 exclusive
  assert.equal(isWithinWorkHours(new Date("2026-09-14T06:00:00"), window), true);
  assert.equal(isWithinWorkHours(new Date("2026-09-14T20:00:00"), window), false);
});

test("workHours: janela vazia e config ausente NUNCA coletam (fail-closed)", () => {
  assert.equal(isWithinWorkHours(new Date("2026-09-14T12:00:00"), { start: "08:00", end: "08:00" }), false);
  assert.equal(isWithinWorkHours(new Date("2026-09-14T12:00:00"), null), false);
  assert.equal(isWithinWorkHours(new Date("2026-09-14T12:00:00"), "lixo"), false);
});

test("workHours: janela cruzando meia-noite (18:00-02:00)", () => {
  const window = { start: "18:00", end: "02:00" };
  assert.equal(isWithinWorkHours(new Date("2026-09-14T23:00:00"), window), true);
  assert.equal(isWithinWorkHours(new Date("2026-09-14T01:00:00"), window), true);
  assert.equal(isWithinWorkHours(new Date("2026-09-14T15:00:00"), window), false);
});

test("workHours: parser aceita string HH:MM-HH:MM do desktop", () => {
  assert.deepEqual(parseWindow("06:00-20:00"), { start: "06:00", end: "20:00" });
  assert.equal(parseWindow("25:00-20:00"), null);
  assert.deepEqual(parseWindow(DEFAULT_WORK_WINDOW), DEFAULT_WORK_WINDOW);
});

// ── offlineQueue ─────────────────────────────────────────────

function memoryStorage(): QueueStorage & { items: QueueItem[] } {
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

test("offlineQueue: enfileira com client_action_id e status pending", () => {
  const storage = memoryStorage();
  let clock = 1_000;
  const queue = new OfflineQueue(storage, () => clock, () => "act-1");
  const item = queue.enqueue("complete", "del-1", { proof: "photo.jpg" });
  assert.equal(item.client_action_id, "act-1");
  assert.equal(item.status, "pending");
  assert.equal(queue.count().pending, 1);
});

test("offlineQueue: flush com sucesso marca synced", async () => {
  const storage = memoryStorage();
  const queue = new OfflineQueue(storage, () => 1_000, () => "act-1");
  queue.enqueue("start", "del-1");
  const result = await queue.flush(async () => undefined);
  assert.deepEqual(result, { sent: 1, failed: 0 });
  assert.equal(queue.count().synced, 1);
});

test("offlineQueue: falha reenfileira com backoff exponencial (cap 5min)", async () => {
  const storage = memoryStorage();
  let clock = 1_000;
  const queue = new OfflineQueue(storage, () => clock, () => "act-1");
  queue.enqueue("fail", "del-1");
  const fail = async () => {
    throw new Error("sem rede");
  };

  await queue.flush(fail); // tentativa 1 → backoff 2s
  let item = storage.items[0];
  assert.equal(item.attempts, 1);
  assert.equal(item.nextAttemptAt - clock, 2_000);

  clock = item.nextAttemptAt;
  await queue.flush(fail); // tentativa 2 → backoff 4s
  item = storage.items[0];
  assert.equal(item.attempts, 2);
  assert.equal(item.nextAttemptAt - clock, 4_000);

  clock = item.nextAttemptAt;
  for (let i = 0; i < 10; i++) {
    clock = item.nextAttemptAt;
    await queue.flush(fail);
    item = storage.items[0];
  }
  assert.equal(item.nextAttemptAt - clock, 300_000, "backoff caps em 5 minutos");
  // enquanto o backoff não vence, pending() não devolve nada
  clock = item.nextAttemptAt - 1;
  assert.equal(queue.pending().length, 0);
});

test("offlineQueue: itens pendentes só saem quando nextAttemptAt chega", () => {
  const storage = memoryStorage();
  let clock = 1_000;
  const queue = new OfflineQueue(storage, () => clock, () => "act-1");
  queue.enqueue("start", "del-1");
  clock = 1_500;
  assert.equal(queue.pending().length, 1);
});

// ── connection fallback ──────────────────────────────────────

function fakeFetch(aliveFor: (url: string) => boolean): typeof fetch {
  return (async (input: RequestInfo | URL) => {
    if (!aliveFor(String(input))) throw new Error("ECONNREFUSED");
    return { ok: true } as Response;
  }) as unknown as typeof fetch;
}

test("connection: prefere LAN, cai para nuvem, depois offline", async () => {
  const targets = {
    lan: { baseUrl: "http://192.168.0.10:8000" },
    cloud: { baseUrl: "https://relay.test" },
  };
  const allAlive = fakeFetch(() => true);
  const lan = await resolveConnection(targets, allAlive);
  assert.equal(lan.mode, "lan");

  // LAN morta → nuvem responde
  const lanDown = await resolveConnection(
    { ...targets, lan: { baseUrl: "http://dead.lan:8000" } },
    fakeFetch((url) => !url.includes("dead.lan")),
  );
  assert.equal(lanDown.mode, "cloud");

  // Tudo morto → offline
  const allDown = await resolveConnection(
    { lan: { baseUrl: "http://dead.lan:8000" }, cloud: { baseUrl: "https://dead.relay" } },
    fakeFetch(() => false),
  );
  assert.equal(allDown.mode, "offline");
  assert.equal(allDown.baseUrl, null);
});
