/**
 * Testes F2 — consentimento LGPD (gate) e replay da fila offline.
 * Rodam com `node --test` (lógica pura + zustand isomórfico, sem RN).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { useSessionStore, loadPersistedConsent, setConsentStorage, createMemoryConsentStorage, createAsyncStorageConsentStorage, CONSENT_STORAGE_KEY, CONSENT_VERSION } from "../src/logic/session.ts";
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
    // O backend consulta idempotency_key em ActionRequest.
    const body = JSON.parse(String(init?.body ?? "{}")) as { idempotency_key?: string };
    assert.ok(body.idempotency_key, "ação deve carregar idempotency_key");
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
    const body = JSON.parse(String(init?.body ?? "{}")) as { idempotency_key?: string };
    if (seen.includes(String(body.idempotency_key))) {
      throw new Error("DUPLICATA enviada ao servidor");
    }
    seen.push(String(body.idempotency_key));
    return { ok: true, json: async () => ({}) } as Response;
  }) as unknown as typeof fetch;

  // Dois flushes seguidos (ex.: replay disparado duas vezes ao reconectar)
  const transport = (i: QueueItem) => postDeliveryAction(fetchFn, "http://base", "tok", { deliveryId: i.deliveryId, action: i.kind === "location" ? "start" : i.kind, clientActionId: i.client_action_id, payload: i.payload });
  await queue.flush(transport);
  await queue.flush(transport);

  assert.equal(seen.length, 1, "segundo flush não reenvia item já synced");
});

// ── P1-1: consentimento persistido no AsyncStorage ───────────

function fakeAsyncStorage(initial: Record<string, string> = {}) {
  const data = new Map<string, string>(Object.entries(initial));
  return {
    data,
    getItem: async (key: string) => data.get(key) ?? null,
    setItem: async (key: string, value: string) => {
      data.set(key, value);
    },
  };
}

test("consent: AsyncStorage persiste o aceite e sobrevive ao restart", async () => {
  const backend = fakeAsyncStorage();
  setConsentStorage(createAsyncStorageConsentStorage(backend));

  resetStore();
  useSessionStore.getState().acceptConsent(new Date("2026-10-30T09:00:00Z"));
  await new Promise((r) => setTimeout(r, 0));

  // ── app reaberto: mesmo AsyncStorage, store zerado ──
  resetStore();
  useSessionStore.getState().setConsentLoaded();
  assert.equal(useSessionStore.getState().hasValidConsent(), false);

  setConsentStorage(createAsyncStorageConsentStorage(backend));
  await loadPersistedConsent();

  const s = useSessionStore.getState();
  assert.equal(s.consentVersion, CONSENT_VERSION);
  assert.equal(s.hasValidConsent(), true);
  assert.ok(s.consentAcceptedAt?.startsWith("2026-10-30"));
});

test("consent: payload corrompido não vira aceite (fail-closed)", async () => {
  const backend = fakeAsyncStorage({ [CONSENT_STORAGE_KEY]: "{nao-e-json" });
  setConsentStorage(createAsyncStorageConsentStorage(backend));

  resetStore();
  await loadPersistedConsent();

  const s = useSessionStore.getState();
  assert.equal(s.consentLoaded, true);
  assert.equal(s.hasValidConsent(), false);
});

test("consent: falha de gravação NÃO vira aceite no próximo boot (fail-closed)", async () => {
  const broken = {
    getItem: async () => null,
    setItem: async () => {
      throw new Error("armazenamento indisponível");
    },
  };
  setConsentStorage(createAsyncStorageConsentStorage(broken));

  resetStore();
  useSessionStore.getState().acceptConsent(new Date("2026-10-30T09:00:00Z"));
  // estado em memória vale para a sessão corrente…
  assert.equal(useSessionStore.getState().hasValidConsent(), true);
  await new Promise((r) => setTimeout(r, 0));

  // …mas nada foi gravado ⇒ no boot seguinte o gate pede de novo.
  resetStore();
  await loadPersistedConsent();
  assert.equal(useSessionStore.getState().hasValidConsent(), false);
  assert.equal(useSessionStore.getState().consentLoaded, true, "boot não fica travado");
});

test("consent: logout encerra a sessão mas preserva o aceite do aparelho", async () => {
  const backend = fakeAsyncStorage();
  setConsentStorage(createAsyncStorageConsentStorage(backend));

  resetStore();
  useSessionStore.getState().acceptConsent(new Date("2026-10-30T09:00:00Z"));
  await new Promise((r) => setTimeout(r, 0));

  useSessionStore.getState().clearSession();
  assert.equal(useSessionStore.getState().accessToken, null, "token saiu");
  assert.equal(useSessionStore.getState().hasValidConsent(), true, "aceite é do aparelho, não da sessão");

  resetStore();
  await loadPersistedConsent();
  assert.equal(useSessionStore.getState().hasValidConsent(), true);
});

test("consent: leitura que falha não destrói o armazenamento e se recupera", async () => {
  const flaky = {
    fail: true,
    data: new Map<string, string>(),
    async getItem(key: string) {
      if (this.fail) throw new Error("io temporário");
      return this.data.get(key) ?? null;
    },
    async setItem(key: string, value: string) {
      this.data.set(key, value);
    },
  };
  setConsentStorage(createAsyncStorageConsentStorage(flaky));

  resetStore();
  await loadPersistedConsent();
  assert.equal(useSessionStore.getState().hasValidConsent(), false, "fail-closed na falha");

  flaky.fail = false; // storage volta
  useSessionStore.getState().acceptConsent(new Date("2026-10-30T09:00:00Z"));
  await new Promise((r) => setTimeout(r, 0));
  resetStore();
  await loadPersistedConsent();
  assert.equal(useSessionStore.getState().hasValidConsent(), true, "recuperou sem recriar nada");
});
