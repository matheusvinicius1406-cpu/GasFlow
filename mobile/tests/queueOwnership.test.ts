/**
 * Fila offline — durabilidade, identidade e replay (prompt 3.1/3.2/3.3).
 *
 * Regras provadas aqui:
 * - logout NÃO apaga ação pendente (perda de trabalho operacional é proibida);
 * - ação de um motorista nunca é reproduzida sob a sessão de outro;
 * - item sem proprietário é adotado só quando a identidade é resolvida;
 * - `flush` só retorna depois da gravação durável concluir;
 * - descarte acontece apenas por decisão explícita, rastreável;
 * - o item offline nunca carrega token/credencial;
 * - concorrência (dois flushes simultâneos) não duplica envio.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { OfflineQueue, ownerMatches, type QueueOwner } from "../src/logic/offlineQueue.ts";
import {
  PersistentQueueStorage,
  MAX_PERSISTED_LOCATIONS,
  createMemoryAsyncKV,
  type AsyncKV,
} from "../src/logic/queuePersistence.ts";

const MARIO: QueueOwner = { driverId: "drv_1", tenantId: "marcos_gas" };
const OUTRO: QueueOwner = { driverId: "drv_2", tenantId: "outra_distribuidora" };

function failingKV(inner: AsyncKV, failNext: { on: boolean }): AsyncKV {
  return {
    getItem: (k) => inner.getItem(k),
    setItem: async (k, v) => {
      if (failNext.on) throw new Error("disco cheio");
      await inner.setItem(k, v);
    },
  };
}

describe("fila offline — identidade e logout", () => {
  it("logout preserva ações pendentes e bloqueia o replay de outra sessão", async () => {
    const kv = createMemoryAsyncKV();
    const storage = new PersistentQueueStorage(kv);
    storage.setSessionOwner(MARIO);
    const queue = new OfflineQueue(storage, () => 1_000, () => "act-1");
    queue.enqueue("complete", "d1", {}, MARIO);
    await storage.whenIdle();

    // ── logout: sessão sai, fila fica ──
    storage.setSessionOwner(null);
    assert.equal(storage.all().length, 1, "logout não pode apagar a ação");

    // ── outro motorista loga: nada é reproduzido ──
    const sentTo: string[] = [];
    const r1 = await queue.flush(
      async (i) => {
        sentTo.push(i.deliveryId);
      },
      { owner: OUTRO },
    );
    assert.deepEqual(r1, { sent: 0, failed: 0 });
    assert.equal(sentTo.length, 0, "replay indevido bloqueado");
    assert.equal(storage.all()[0].status, "pending", "ação segue pendente, preservada");
    assert.equal(storage.heldForOtherOwner(OUTRO).length, 1, "visível como retida");

    // ── o dono volta: a ação sincroniza ──
    const r2 = await queue.flush(async () => undefined, { owner: MARIO });
    assert.deepEqual(r2, { sent: 1, failed: 0 });
    assert.equal(storage.all()[0].status, "synced");
    // nada foi apagado em nenhum momento
    assert.equal(storage.getDiscards().length, 0, "descarte só por decisão explícita");
  });

  it("item sem proprietário não é reproduzido até a identidade ser resolvida", async () => {
    const storage = new PersistentQueueStorage(createMemoryAsyncKV());
    const queue = new OfflineQueue(storage, () => 1_000, () => "act-orphan");
    queue.enqueue("start", "d9"); // enfileirado antes do /driver/me responder
    await storage.whenIdle();

    const calls: string[] = [];
    const blocked = await queue.flush(
      async (i) => {
        calls.push(i.deliveryId);
      },
      { owner: MARIO },
    );
    assert.deepEqual(blocked, { sent: 0, failed: 0 });
    assert.equal(calls.length, 0, "sem owner não há replay");
    assert.equal(storage.heldForOtherOwner(MARIO).length, 1);

    // identidade resolvida ⇒ adoção explícita ⇒ replay
    assert.equal(storage.claimUnowned(MARIO), 1);
    const ok = await queue.flush(
      async (i) => {
        calls.push(i.deliveryId);
      },
      { owner: MARIO },
    );
    assert.deepEqual(ok, { sent: 1, failed: 0 });
    assert.deepEqual(calls, ["d9"]);
    // segunda adoção não duplica
    assert.equal(storage.claimUnowned(MARIO), 0);
  });

  it("identidade de outra sessão não adota itens órfãos", () => {
    const storage = new PersistentQueueStorage(createMemoryAsyncKV());
    storage.save({
      client_action_id: "act-x",
      kind: "start",
      deliveryId: "d1",
      payload: {},
      status: "pending",
      attempts: 0,
      nextAttemptAt: 0,
      createdAt: 1,
      // sem owner
    });
    // sessão já sabe quem é o dono da fila (caso típico: snapshot persistido)
    storage.setSessionOwner(MARIO);
    assert.equal(storage.claimUnowned(OUTRO), 0, "outro motorista não adota a fila");
    assert.equal(storage.all()[0].owner, undefined, "item continua sem dono");
    assert.equal(storage.claimUnowned(MARIO), 1, "o dono resolve a identidade e adota");
    assert.equal(storage.all()[0].owner?.driverId, "drv_1");
  });

  it("o item offline nunca carrega token nem credencial", async () => {
    const storage = new PersistentQueueStorage(createMemoryAsyncKV());
    const queue = new OfflineQueue(storage, () => 1_000, () => "act-clean");
    queue.enqueue("complete", "d1", { proof_type: "CODE" }, MARIO);
    await storage.whenIdle();

    const raw = JSON.stringify({ owner: storage.all()[0].owner, payload: storage.all()[0].payload });
    assert.equal(/token|bearer|password|senha|authorization/i.test(raw), false);
    assert.deepEqual(storage.all()[0].owner, MARIO);
  });

  it("ownerMatches exige mesmo motorista (e tenant quando os dois têm)", () => {
    assert.equal(ownerMatches(MARIO, MARIO), true);
    assert.equal(ownerMatches(MARIO, OUTRO), false);
    assert.equal(ownerMatches(MARIO, { driverId: "drv_1" }), true, "tenant ausente casa");
    assert.equal(ownerMatches(MARIO, { driverId: "drv_1", tenantId: "outra" }), false);
    assert.equal(ownerMatches(undefined, MARIO), false);
    assert.equal(ownerMatches(MARIO, undefined), false);
  });

  it("a identidade da sessão é persistida e sobrevive ao restart", async () => {
    const kv = createMemoryAsyncKV();
    const first = new PersistentQueueStorage(kv);
    first.setSessionOwner(MARIO);
    await first.whenIdle();

    const second = new PersistentQueueStorage(kv);
    await second.hydrate();
    assert.deepEqual(second.getSessionOwner(), MARIO);
  });
});

describe("fila offline — durabilidade da gravação", () => {
  it("flush só retorna depois da escrita durável (snapshot já contém synced)", async () => {
    const kv = createMemoryAsyncKV();
    const storage = new PersistentQueueStorage(kv);
    const queue = new OfflineQueue(storage, () => 1_000, () => "act-durable");
    queue.enqueue("arrive", "d1", {}, MARIO);

    await queue.flush(async () => undefined, { owner: MARIO });

    // No instante em que flush resolve, o disco já tem o estado final.
    const raw = await kv.getItem("gasflow.driver.queue.v1");
    assert.ok(raw, "snapshot gravado");
    const parsed = JSON.parse(raw) as {
      schema: number;
      items: Array<{ status: string; client_action_id: string }>;
    };
    const item = parsed.items.find((i) => i.client_action_id === "act-durable");
    assert.equal(item?.status, "synced");
    assert.equal(parsed.schema, 1, "payload versionado");
  });

  it("persist() propaga falha de escrita em vez de fingir sucesso", async () => {
    const failNext = { on: true };
    const storage = new PersistentQueueStorage(failingKV(createMemoryAsyncKV(), failNext));
    new OfflineQueue(storage, () => 1_000, () => "act-fail").enqueue("start", "d1");

    await storage.whenIdle();
    await assert.rejects(() => storage.persist(), /não pôde ser gravada/);

    failNext.on = false; // disco volta
    await storage.persist(); // nova tentativa grava e resolve
    assert.equal(storage.lastWriteError, null);
    assert.equal(storage.all().length, 1, "a ação em memória nunca se perdeu");
  });

  it("gravações concorrentes não se sobrescrevem (último estado vence íntegro)", async () => {
    const kv = createMemoryAsyncKV();
    const storage = new PersistentQueueStorage(kv);
    const queue = new OfflineQueue(storage, () => 1_000);

    const ids = ["a", "b", "c", "d", "e"];
    for (const id of ids) queue.enqueue("start", `d-${id}`, {}, MARIO);
    await storage.persist();

    const parsed = JSON.parse((await kv.getItem("gasflow.driver.queue.v1")) as string) as {
      items: Array<{ deliveryId: string }>;
    };
    assert.equal(parsed.items.length, 5, "nenhuma escrita concorrente perdeu item");
    assert.deepEqual(
      parsed.items.map((i) => i.deliveryId).sort(),
      ["d-a", "d-b", "d-c", "d-d", "d-e"],
    );
  });

  it("dois flushes simultâneos não duplicam o envio", async () => {
    const kv = createMemoryAsyncKV();
    const storage = new PersistentQueueStorage(kv);
    const queue = new OfflineQueue(storage, () => 1_000, () => "act-parallel");
    queue.enqueue("complete", "d1", {}, MARIO);

    const calls: string[] = [];
    let inFlight = 0;
    const transport = async () => {
      inFlight += 1;
      assert.equal(inFlight, 1, "transporte concorrente detectado");
      await new Promise((r) => setTimeout(r, 5));
      calls.push("sent");
      inFlight -= 1;
    };

    const [a, b] = await Promise.all([
      queue.flush(transport, { owner: MARIO }),
      queue.flush(transport, { owner: MARIO }),
    ]);
    // O item só pode ter sido aceito uma vez (o segundo flush o vê já synced
    // ou fora de `pending`, pois a fila é serializada por item).
    assert.equal(calls.length, 1, `envio duplicado: ${calls.length}`);
    assert.equal(a.sent + b.sent, 1);
  });
});

describe("fila offline — retenção e descarte", () => {
  it("teto de posições: as mais antigas já sincronizadas saem, ações nunca", () => {
    const storage = new PersistentQueueStorage(createMemoryAsyncKV());
    const queue = new OfflineQueue(storage, () => 1_000);
    queue.enqueue("complete", "d-acao", {}, MARIO);
    for (let i = 0; i < MAX_PERSISTED_LOCATIONS + 50; i += 1) {
      const loc = queue.enqueue("location", "", { recorded_at: `2026-10-30T10:00:${i % 60}s` });
      loc.status = "synced";
      storage.save(loc);
    }

    const all = storage.all();
    assert.ok(all.length <= MAX_PERSISTED_LOCATIONS + 1, `teto aplicado: ${all.length}`);
    assert.equal(
      all.some((i) => i.kind === "complete" && i.deliveryId === "d-acao"),
      true,
      "ação de entrega nunca é podada pelo teto de posições",
    );
  });

  it("descarte exige decisão explícita e fica registrado com motivo", () => {
    const storage = new PersistentQueueStorage(createMemoryAsyncKV());
    const queue = new OfflineQueue(storage, () => 1_000, () => "act-del");
    const item = queue.enqueue("fail", "d1", {}, MARIO);

    assert.equal(storage.discard("inexistente", "motivo"), false);
    assert.equal(storage.discard(item.client_action_id, "entrega cancelada pelo operador"), true);

    assert.equal(storage.all().length, 0);
    const audit = storage.getDiscards();
    assert.equal(audit.length, 1);
    assert.equal(audit[0].reason, "entrega cancelada pelo operador");
    assert.equal(audit[0].kind, "fail");
  });
});
