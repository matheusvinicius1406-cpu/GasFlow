/**
 * Fase 5.2 — fila offline de rastreio.
 *
 * Cobre o que foi estendido no OfflineQueue para posições:
 * - dedupe por `recorded_at` (replay do background não empilha o mesmo ponto)
 * - retenção local de 7 dias (descarte de enviados/vencidos)
 * - nenhuma ação de entrega é afetada
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  LOCATION_RETENTION_DAYS,
  OfflineQueue,
  type QueueItem,
  type QueueStorage,
} from "../src/logic/offlineQueue.ts";

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
    remove: (id) => {
      const idx = items.findIndex((i) => i.client_action_id === id);
      if (idx >= 0) items.splice(idx, 1);
    },
  };
}

describe("Fase 5 — fila offline de posições", () => {
  it("deduplica posições pelo recorded_at", () => {
    const storage = memoryStorage();
    const queue = new OfflineQueue(storage, () => 1_000);

    const first = queue.enqueue("location", "", { latitude: -23.5, recorded_at: "2026-09-22T12:00:00Z" });
    const again = queue.enqueue("location", "", { latitude: -23.5, recorded_at: "2026-09-22T12:00:00Z" });

    assert.equal(storage.items.length, 1);
    assert.equal(again.client_action_id, first.client_action_id);
  });

  it("mantém posições de horários diferentes", () => {
    const storage = memoryStorage();
    const queue = new OfflineQueue(storage, () => 1_000);

    queue.enqueue("location", "", { recorded_at: "2026-09-22T12:00:00Z" });
    queue.enqueue("location", "", { recorded_at: "2026-09-22T12:00:30Z" });

    assert.equal(storage.items.length, 2);
  });

  it("não deduplica ações que não são posição", () => {
    const storage = memoryStorage();
    const queue = new OfflineQueue(storage, () => 1_000);

    queue.enqueue("start", "d1", { recorded_at: "2026-09-22T12:00:00Z" });
    queue.enqueue("start", "d1", { recorded_at: "2026-09-22T12:00:00Z" });

    assert.equal(storage.items.length, 2);
  });

  it("pruneLocations descarta posições já enviadas", () => {
    const storage = memoryStorage();
    const queue = new OfflineQueue(storage, () => 1_000);
    const sent = queue.enqueue("location", "", { recorded_at: "2026-09-22T12:00:00Z" });
    queue.enqueue("location", "", { recorded_at: "2026-09-22T12:00:30Z" });
    sent.status = "synced";
    storage.save(sent);

    const removed = queue.pruneLocations();

    assert.equal(removed, 1);
    assert.equal(queue.count().pending, 1);
  });

  it("pruneLocations expira posições mais velhas que a retenção (7 dias)", () => {
    let clock = Date.parse("2026-09-22T12:00:00Z");
    const storage = memoryStorage();
    const queue = new OfflineQueue(storage, () => clock);

    const old = queue.enqueue("location", "", { recorded_at: "2026-09-01T12:00:00Z" });
    queue.enqueue("location", "", { recorded_at: "2026-09-22T10:00:00Z" });
    // Envelhece a posição depois de enfileirar (o enqueue também poda).
    old.createdAt = clock - (LOCATION_RETENTION_DAYS + 2) * 24 * 60 * 60 * 1000;
    storage.save(old);

    const removed = queue.pruneLocations();

    assert.equal(removed, 1);
    assert.equal(storage.items.length, 1);
  });

  it("pruneLocations não mexe em ações de entrega", () => {
    const storage = memoryStorage();
    const queue = new OfflineQueue(storage, () => 1_000);
    const action = queue.enqueue("complete", "d1", { proof_type: "NONE" });
    action.status = "synced";
    storage.save(action);

    assert.equal(queue.pruneLocations(), 0);
    assert.equal(storage.items.length, 1);
  });
});
