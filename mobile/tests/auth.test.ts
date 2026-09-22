/**
 * Testes do fluxo migrado do app do entregador (Fase 2).
 *
 * Cobrem o que a Fase 1 introduziu no backend e o app passou a consumir:
 * login pela auth principal, gate de troca de senha (HTTP 403 e WS 4003),
 * custódia do token e persistência de sessão.
 *
 * Módulos puros — rodam com `node --test` (sem RN).
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  operatorLogin,
  changePassword,
  fetchMyDeliveries,
  driverWsUrl,
  PasswordChangeRequiredError,
} from "../src/logic/api.ts";
import { attachDriverSocket, reconnectDelay } from "../src/logic/realtime.ts";
import {
  createMemoryTokenStorage,
  createKeychainTokenStorage,
  setTokenStorage,
  getTokenStorage,
  type KeychainLike,
} from "../src/logic/tokenStorage.ts";
import { useSessionStore, restorePersistedSession } from "../src/logic/session.ts";

// ── Helpers ─────────────────────────────────────────────────

function jsonResponse(body: unknown, init: { status?: number; headers?: Record<string, string> } = {}) {
  const headers = init.headers ?? {};
  return {
    ok: (init.status ?? 200) < 400,
    status: init.status ?? 200,
    headers: { get: (k: string) => headers[k] ?? headers[k.toLowerCase()] ?? null },
    json: async () => body,
  } as unknown as Response;
}

function restoreSessionBaseline() {
  useSessionStore.setState({
    accessToken: null,
    refreshToken: null,
    driverId: null,
    username: null,
    mustChangePassword: false,
    consentAcceptedAt: null,
    consentVersion: null,
    consentLoaded: false,
  });
  setTokenStorage(createMemoryTokenStorage());
}

// ── Login (auth principal) ──────────────────────────────────

test("login: POST /auth/login com platform=mobile e devolve os tokens", async () => {
  let captured: { url: string; body: unknown } | null = null;
  const fetchFn = (async (url: string, init: RequestInit) => {
    captured = { url, body: JSON.parse(String(init.body)) };
    return jsonResponse({
      access_token: "acc",
      refresh_token: "ref",
      role: "DRIVER",
      tenant_id: "default",
      user: { id: "u1", username: "drv_1", must_change_password: true },
    });
  }) as unknown as typeof fetch;

  const result = await operatorLogin(fetchFn, "http://dep:8000/", "drv_1", "Temp#1234");

  assert.equal(captured!.url, "http://dep:8000/auth/login");
  assert.deepEqual(captured!.body, { username: "drv_1", password: "Temp#1234", platform: "mobile" });
  assert.equal(result.access_token, "acc");
  assert.equal(result.user.must_change_password, true);
});

// ── Gate de troca de senha (HTTP) ───────────────────────────

test("gate: 403 com header X-GasFlow-Password-Change-Required vira erro tipado", async () => {
  const fetchFn = (async () =>
    jsonResponse(
      { detail: "Password change required" },
      { status: 403, headers: { "X-GasFlow-Password-Change-Required": "1" } },
    )) as unknown as typeof fetch;

  await assert.rejects(() => fetchMyDeliveries(fetchFn, "http://dep:8000", "tok"), PasswordChangeRequiredError);
});

test("gate: 403 sem header mas com detail equivalente também vira erro tipado", async () => {
  const fetchFn = (async () =>
    jsonResponse({ detail: "Password change required" }, { status: 403 })) as unknown as typeof fetch;

  await assert.rejects(() => fetchMyDeliveries(fetchFn, "http://dep:8000", "tok"), PasswordChangeRequiredError);
});

test("gate: 403 comum (permissão) NÃO vira erro de senha", async () => {
  const fetchFn = (async () =>
    jsonResponse({ detail: "Driver access required" }, { status: 403 })) as unknown as typeof fetch;

  await assert.rejects(
    () => fetchMyDeliveries(fetchFn, "http://dep:8000", "tok"),
    (err: unknown) => err instanceof Error && !(err instanceof PasswordChangeRequiredError),
  );
});

// ── change-password e listagem ──────────────────────────────

test("change-password: POST /auth/change-password com as duas senhas", async () => {
  let url = "";
  let body: Record<string, string> = {};
  const fetchFn = (async (u: string, init: RequestInit) => {
    url = u;
    body = JSON.parse(String(init.body));
    return jsonResponse({ success: true });
  }) as unknown as typeof fetch;

  await changePassword(fetchFn, "http://dep:8000", "tok", "Temp#1234", "NovaSenha123");
  assert.equal(url, "http://dep:8000/auth/change-password");
  assert.deepEqual(body, { current_password: "Temp#1234", new_password: "NovaSenha123" });
});

test("deliveries: usa /driver/deliveries e normaliza o DeliveryRecord", async () => {
  let url = "";
  const fetchFn = (async (u: string) => {
    url = u;
    return jsonResponse({
      deliveries: [
        {
          id: "dlv-1",
          customer_name: "Maria",
          status: "ASSIGNED",
          address: { street: "Rua A", number: "10", neighborhood: "Centro", city: "Belém" },
        },
      ],
    });
  }) as unknown as typeof fetch;

  const list = await fetchMyDeliveries(fetchFn, "http://dep:8000", "tok");
  assert.equal(url, "http://dep:8000/driver/deliveries");
  assert.equal(list[0].delivery_id, "dlv-1");
  assert.equal(list[0].customer_name, "Maria");
  assert.match(list[0].address, /Rua A, 10/);
});

test("ws url: converte http→ws e codifica o token", () => {
  assert.equal(driverWsUrl("https://dep.gasflow/app", "a b/c"), "wss://dep.gasflow/app/ws?token=a%20b%2Fc");
});

// ── Realtime (WS 4003) ──────────────────────────────────────

function fakeSocket() {
  return {
    closed: false,
    close() {
      this.closed = true;
    },
    onopen: null as unknown,
    onmessage: null as unknown,
    onclose: null as unknown,
    onerror: null as unknown,
  };
}

test("realtime: fechamento 4003 levanta o gate e NÃO reconecta", () => {
  const socket = fakeSocket();
  let gate = false;
  let closed = 0;
  const ctrl = attachDriverSocket({
    socket,
    onPasswordChangeRequired: () => {
      gate = true;
    },
    onClose: () => {
      closed += 1;
    },
  });

  (socket.onclose as (ev: { code: number }) => void)({ code: 4003 });
  assert.equal(gate, true);
  assert.equal(closed, 0, "não deve tratar 4003 como fechamento comum");
  assert.equal(ctrl.stoppedByPasswordGate(), true);
});

test("realtime: fechamento comum reporta código e mensagem JSON é parseada", () => {
  const socket = fakeSocket();
  const events: unknown[] = [];
  let closedCode = -1;
  attachDriverSocket({ socket, onEvent: (e) => events.push(e), onClose: (c) => (closedCode = c) });

  (socket.onmessage as (ev: { data: unknown }) => void)({ data: JSON.stringify({ type: "event" }) });
  (socket.onclose as (ev: { code: number }) => void)({ code: 1006 });

  assert.deepEqual(events[0], { type: "event" });
  assert.equal(closedCode, 1006);
});

test("realtime: backoff exponencial com teto", () => {
  assert.equal(reconnectDelay(0, 1000, 30000), 1000);
  assert.equal(reconnectDelay(2, 1000, 30000), 4000);
  assert.equal(reconnectDelay(10, 1000, 30000), 30000);
});

// ── Token storage ───────────────────────────────────────────

test("tokenStorage: adapter de Keychain guarda/limpa por serviço", async () => {
  const store = new Map<string, string>();
  const keychain: KeychainLike = {
    async setGenericPassword(_u, password) {
      store.set("svc", password);
    },
    async getGenericPassword() {
      return store.has("svc") ? { password: store.get("svc") } : false;
    },
    async resetGenericPassword() {
      store.clear();
    },
  };
  const storage = createKeychainTokenStorage(keychain);
  await storage.set("tok-1");
  assert.equal(await storage.get(), "tok-1");
  await storage.clear();
  assert.equal(await storage.get(), null);
});

// ── Sessão persistida ───────────────────────────────────────

test("sessão: setSession persiste o token; restore reidrata; clear apaga", async () => {
  restoreSessionBaseline();

  useSessionStore.getState().setSession({ access_token: "acc", refresh_token: "ref", driver_id: "000001" });
  assert.equal(await getTokenStorage().get(), "acc");

  // Reabrir o app: zera o estado e restaura do storage.
  useSessionStore.setState({ accessToken: null });
  const restored = await restorePersistedSession();
  assert.equal(restored, true);
  assert.equal(useSessionStore.getState().accessToken, "acc");

  useSessionStore.getState().clearSession();
  assert.equal(await getTokenStorage().get(), null);
  assert.equal(useSessionStore.getState().accessToken, null);
});

test("sessão: mustChangePassword é estado do store (gate)", () => {
  restoreSessionBaseline();
  useSessionStore.getState().setMustChangePassword(true);
  assert.equal(useSessionStore.getState().mustChangePassword, true);
  useSessionStore.getState().clearSession();
  assert.equal(useSessionStore.getState().mustChangePassword, false);
});
