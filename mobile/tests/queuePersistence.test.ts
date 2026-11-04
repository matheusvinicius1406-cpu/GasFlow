/**
 * Fila offline persistente — prova de sobrevivência ao fechamento do app.
 *
 * O "restart" é simulado criando um segundo storage sobre o MESMO KV: é
 * exatamente o que AsyncStorage faz (processo novo, mesmo arquivo). O teste
 * falha se a fila depender de variável em memória do processo anterior.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { OfflineQueue, type QueueItem } from "../src/logic/offlineQueue.ts";
import {
  PersistentQueueStorage,
  QUEUE_STORAGE_KEY,
  createMemoryAsyncKV,
  type AsyncKV,
} from "../src/logic/queuePersistence.ts";

function countingKV(inner: AsyncKV = createMemoryAsyncKV()) {
  const stats = { writes: 0, writes_at: [] as string[] };
  return {
    stats,
    kv: inner,
    wrapper: {
      getItem: (key: string) => inner.getItem(key),
      setItem: async (key: string, value: string) => {
        stats.writes += 1;
        stats.writes_at.push(value);
        await inner.setItem(key, value);
      },
    } satisfies AsyncKV,
  };
}

describe("fila offline persistente", () => {
  it("sobrevive ao restart do app e reenvia uma única vez", async () => {
    const { kv } = countingKV();
    const before = new PersistentQueueStorage(kv);
    const queueBefore = new OfflineQueue(before, () => 1_000, () => "act-1");

    queueBefore.enqueue("complete", "delivery-1", { proof_type: "NONE" });
    await before.whenIdle();

    // ── app fechado e reaberto: novo storage, mesmo KV ──
    const after = new PersistentQueueStorage(kv);
    const queueAfter = new OfflineQueue(after);
    await after.hydrate();

    const pending = queueAfter.pending();
    assert.equal(pending.length, 1);
    assert.equal(pending[0].client_action_id, "act-1");
    assert.equal(pending[0].deliveryId, "delivery-1");
    assert.equal(pending[0].kind, "complete");

    const sent: QueueItem[] = [];
    const result = await queueAfter.flush(async (item) => {
      sent.push(item);
      // servidor confirmou: só a primeira chamada pode acontecer
      if (sent.length > 1) throw new Error("reenvio duplicado");
    });
    assert.deepEqual(result, { sent: 1, failed: 0 });
    assert.equal(sent.length, 1);
    await after.whenIdle();

    // ── terceiro boot: nada reenviado ──
    const again = new PersistentQueueStorage(kv);
    await again.hydrate();
    assert.equal(again.all().length, 1);
    assert.equal(again.all()[0].status, "synced");
    assert.equal(new OfflineQueue(again).pending().length, 0);
  });

  it("preserva o mesmo client_action_id entre restarts (chave de idempotência)", async () => {
    const { kv } = countingKV();
    const first = new PersistentQueueStorage(kv);
    const item = new OfflineQueue(first, () => 1_000, () => "uuid-estavel").enqueue("start", "d9");
    await first.whenIdle();

    const second = new PersistentQueueStorage(kv);
    await second.hydrate();

    assert.equal(second.all()[0].client_action_id, item.client_action_id);
  });

  it("não ressuscita ação já confirmada pelo servidor", async () => {
    const { kv } = countingKV();
    const first = new PersistentQueueStorage(kv);
    const queue = new OfflineQueue(first, () => 1_000, () => "act-synced");
    queue.enqueue("arrive", "d1");
    await queue.flush(async () => undefined);
    await first.whenIdle();

    const second = new PersistentQueueStorage(kv);
    // ação local nova com mesmo id (não deveria acontecer, mas o merge é defensivo)
    second.save({ ...(second.all()[0] ?? ({} as QueueItem)), client_action_id: "act-synced", status: "pending" } as QueueItem);
    await second.hydrate();

    assert.equal(second.all()[0].status, "synced");
    assert.equal(new OfflineQueue(second).pending().length, 0);
  });

  it("mantém em memória o que foi enfileirado antes da hidratação", async () => {
    const { kv } = countingKV();
    const seed = new PersistentQueueStorage(kv);
    seed.save({
      client_action_id: "persistido",
      kind: "start",
      deliveryId: "d1",
      payload: {},
      status: "pending",
      attempts: 0,
      nextAttemptAt: 0,
      createdAt: 1,
    });
    await seed.whenIdle();

    const boot = new PersistentQueueStorage(kv);
    // enfileirado antes de hydrate() terminar (corrida real de boot)
    boot.save({
      client_action_id: "novo",
      kind: "complete",
      deliveryId: "d2",
      payload: {},
      status: "pending",
      attempts: 0,
      nextAttemptAt: 0,
      createdAt: 2,
    });
    await boot.hydrate();

    assert.deepEqual(
      boot.all().map((i) => i.client_action_id).sort(),
      ["novo", "persistido"],
    );
  });

  it("remove() apaga de verdade e o prune não volta no próximo boot", async () => {
    const { kv } = countingKV();
    const first = new PersistentQueueStorage(kv);
    const queue = new OfflineQueue(first, () => 1_000);
    const loc = queue.enqueue("location", "", { recorded_at: "2026-10-30T10:00:00Z" });
    await queue.flush(async () => undefined);
    assert.equal(queue.pruneLocations(), 1);
    await first.whenIdle();

    const second = new PersistentQueueStorage(kv);
    await second.hydrate();
    assert.equal(second.all().length, 0);
    assert.equal(loc.status /* item original não é fonte de verdade */, "pending");
  });

  it("snapshot corrompido não derruba o boot e é reportado", async () => {
    const broken: AsyncKV = {
      getItem: async () => "{isso não é json",
      setItem: async () => undefined,
    };
    const storage = new PersistentQueueStorage(broken);
    await storage.hydrate();

    assert.equal(storage.all().length, 0);
    assert.equal(storage.lastHydrateError !== null, true);

    // app continua operável: enfileirar e enviar não depende do snapshot
    const queue = new OfflineQueue(storage, () => 1_000);
    queue.enqueue("start", "d1");
    assert.equal((await queue.flush(async () => undefined)).sent, 1);
  });

  it("falha de escrita não perde a fila em memória e é reportada", async () => {
    const flaky: AsyncKV = {
      getItem: async () => null,
      setItem: async () => {
        throw new Error("disco cheio");
      },
    };
    const storage = new PersistentQueueStorage(flaky);
    const queue = new OfflineQueue(storage, () => 1_000);
    queue.enqueue("start", "d1");
    await storage.whenIdle();

    assert.equal(storage.lastWriteError, "disco cheio");
    assert.equal(queue.pending().length, 1);
  });

  it("attach() troca o KV e hidrata do storage definitivo", async () => {
    const memory = new PersistentQueueStorage(createMemoryAsyncKV());
    const local = new OfflineQueue(memory, () => 1_000, () => "act-local").enqueue("start", "d-mem");

    const disk = createMemoryAsyncKV();
    await disk.setItem(
      QUEUE_STORAGE_KEY,
      JSON.stringify([
        {
          client_action_id: "d-disk",
          kind: "complete",
          deliveryId: "d-disk",
          payload: {},
          status: "pending",
          attempts: 0,
          nextAttemptAt: 0,
          createdAt: 1,
        },
      ]),
    );

    await memory.attach(disk);

    assert.equal(memory.isHydrated, true);
    assert.deepEqual(
      memory.all().map((i) => i.client_action_id).sort(),
      ["act-local", "d-disk"],
    );
    assert.equal(memory.all().find((i) => i.client_action_id === local.client_action_id)?.deliveryId, "d-mem");
  });

  it("clear() é operação explícita e persiste o snapshot vazio (logout já não chama)", async () => {
    const { kv } = countingKV();
    const storage = new PersistentQueueStorage(kv);
    new OfflineQueue(storage, () => 1_000).enqueue("start", "d1");
    storage.clear();
    await storage.whenIdle();

    const next = new PersistentQueueStorage(kv);
    await next.hydrate();
    assert.equal(next.all().length, 0);
  });
});
