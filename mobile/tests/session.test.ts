/**
 * Testes F2 — consentimento LGPD (gate) e replay da fila offline.
 * Rodam com `node --test` (lógica pura + zustand isomórfico, sem RN).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { useSessionStore, loadPersistedConsent, setConsentStorage, createMemoryConsentStorage, CONSENT_VERSION } from "../src/logic/session.ts";
import { OfflineQueue, type QueueItem, type QueueStorage } from "../src/logic/offlineQueue.ts";
import { postDeliveryAction } from "../src/logic/api.ts";

// ── Consentimento LGPD (gate do RootNavigator) ───────────────

function resetStore() {
  useSessionStore.setState({
    accessToken: null,
    refreshToken: null,
    driverId: null,
    consentAcceptedAt: null,
    consentVersion: null,
    consentLoaded: false,
  });
}

test("consent: fail-closed — sem consentimento, gate bloqueia (hasValidConsent=false)", () => {
  resetStore();
  const s = useSessionStore.getState();
  assert.equal(s.consentLoaded, false);
  assert.equal(s.hasValidConsent(), false);
});

test("consent: aceitar registra data e versão vigente", () => {
  resetStore();
  useSessionStore.getState().acceptConsent(new Date("2026-09-16T12:00:00Z"));
  const s = useSessionStore.getState();
  assert.equal(s.consentVersion, CONSENT_VERSION);
  assert.equal(s.hasValidConsent(), true);
  assert.ok(s.consentAcceptedAt?.startsWith("2026-09-16"));
});

test("consent: persistido com versão antiga NÃO desbloqueia (pede de novo)", async () => {
  resetStore();
  const storage = createMemoryConsentStorage();
  await storage.set({ acceptedAt: "2026-01-01T00:00:00Z", version: "0.9" });
  setConsentStorage(storage);

  await loadPersistedConsent();
  const s = useSessionStore.getState();
  assert.equal(s.consentLoaded, true);
  assert.equal(s.consentAcceptedAt, null, "termo antigo é descartado");
  assert.equal(s.hasValidConsent(), false);
});

test("consent: persistido na versão vigente desbloqueia direto", async () => {
  resetStore();
  const storage = createMemoryConsentStorage();
  await storage.set({ acceptedAt: "2026-09-16T08:00:00Z", version: CONSENT_VERSION });
  setConsentStorage(storage);

  await loadPersistedConsent();
  const s = useSessionStore.getState();
  assert.equal(s.hasValidConsent(), true);
  assert.equal(s.consentLoaded, true);
});

test("consent: storage quebrado = fail-closed (pede consentimento)", async () => {
  resetStore();
  setConsentStorage({
    get: () => Promise.reject(new Error("storage corrompido")),
    set: () => Promise.resolve(),
  });
  await loadPersistedConsent();
  const s = useSessionStore.getState();
  assert.equal(s.consentLoaded, true);
  assert.equal(s.hasValidConsent(), false);
});

// ── Replay da fila offline ponta a ponta (C4.3) ─────────────

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

function fetchFailingThenOk(attemptsBeforeSuccess: number): { fetchFn: typeof fetch; calls: string[] } {
  let attempt = 0;
  const calls: string[] = [];
  const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push(String(input));
    attempt += 1;
    if (attempt <= attemptsBeforeSuccess) throw new Error("sem rede");
    // valida que o client_action_id foi no corpo (idempotência)
    const body = JSON.parse(String(init?.body ?? "{}")) as { client_action_id?: string };
    assert.ok(body.client_action_id, "ação deve carregar client_action_id");
    return { ok: true, json: async () => ({}) } as Response;
  }) as unknown as typeof fetch;
  return { fetchFn, calls };
}

test("replay: entrega confirmada offline → fila pending → synced ao voltar", async () => {
  const storage = memoryStorage();
  let clock = 1_000;
  const queue = new OfflineQueue(storage, () => clock, () => "act-replay-1");

  // 1. Entregador confirma a entrega SEM rede → enfileira
  const item = queue.enqueue("complete", "del-77", { proof_type: "NONE" });
  assert.equal(queue.count().pending, 1);

  // 2. Flush com rede caída → falha, backoff 2s
  const down = fetchFailingThenOk(99);
  const res1 = await queue.flush((i) => postDeliveryAction(down.fetchFn, "http://base", "tok", { deliveryId: i.deliveryId, action: i.kind === "location" ? "start" : i.kind, clientActionId: i.client_action_id, payload: i.payload }));
  assert.deepEqual(res1, { sent: 0, failed: 1 });
  assert.equal(storage.items[0].status, "pending");

  // 3. Rede volta (e backoff vence) → flush entrega e marca synced
  clock = storage.items[0].nextAttemptAt + 1;
  const up = fetchFailingThenOk(0);
  const res2 = await queue.flush((i) => postDeliveryAction(up.fetchFn, "http://base", "tok", { deliveryId: i.deliveryId, action: i.kind === "location" ? "start" : i.kind, clientActionId: i.client_action_id, payload: i.payload }));
  assert.deepEqual(res2, { sent: 1, failed: 0 });
  assert.equal(storage.items[0].status, "synced");
  assert.equal(queue.count().synced, 1);
});

test("replay: ações NÃO duplicam no servidor (um POST por client_action_id)", async () => {
  const storage = memoryStorage();
  const queue = new OfflineQueue(storage, () => 1_000, () => "act-uniq-1");
  queue.enqueue("start", "del-1");

  const seen: string[] = [];
  const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body ?? "{}")) as { client_action_id?: string };
    if (seen.includes(String(body.client_action_id))) {
      throw new Error("DUPLICATA enviada ao servidor");
    }
    seen.push(String(body.client_action_id));
    return { ok: true, json: async () => ({}) } as Response;
  }) as unknown as typeof fetch;

  // Dois flushes seguidos (ex.: replay disparado duas vezes ao reconectar)
  const transport = (i: QueueItem) => postDeliveryAction(fetchFn, "http://base", "tok", { deliveryId: i.deliveryId, action: i.kind === "location" ? "start" : i.kind, clientActionId: i.client_action_id, payload: i.payload });
  await queue.flush(transport);
  await queue.flush(transport);

  assert.equal(seen.length, 1, "segundo flush não reenvia item já synced");
});
