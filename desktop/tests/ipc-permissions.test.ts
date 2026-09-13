/**
 * Testes do gate de permissão IPC (dist/main/ipc-permissions.js).
 * Node puro (node:test) — sem Electron; o fetcher é injetado.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import Module from "node:module";
import { createRequire } from "node:module";

// Stub do electron ANTES do primeiro require do módulo sob teste.
// Singleton: registerProtectedHandler faz require("electron") a cada chamada —
// o MESMO objeto precisa ser devolvido para o teste ler os handlers.
const electronStub = {
  ipcMain: {
    handlers: new Map<string, Function>(),
    handle(ch: string, fn: Function) {
      this.handlers.set(ch, fn);
    },
  },
};
let electronRequired = false;
const origRequire = Module.prototype.require;
Module.prototype.require = function (this: unknown, id: string) {
  if (id === "electron") {
    electronRequired = true;
    return electronStub;
  }
  return origRequire.apply(this, arguments as unknown as Parameters<typeof origRequire>);
};

const req = createRequire(__filename);
// eslint-disable-next-line @typescript-eslint/no-var-requires
const mod = req("../dist/main/ipc-permissions.js") as {
  registerProtectedHandler: (channel: string, permission: string, handler: Function) => void;
  registerTokenProvider: (provider: (() => string) | null) => void;
  clearPermissionCache: () => void;
  forTesting: () => {
    createPermissionGate: (opts?: { fetchPermissions?: () => Promise<string[]>; cacheTtlMs?: number }) => {
      check: (p: string) => Promise<boolean>;
      checkAndThrow: (p: string) => Promise<void>;
      resetCache: () => void;
      _debug: { stats: () => { cached: boolean } };
    };
    setBackendBaseUrl: (url: string) => void;
  };
};

const { createPermissionGate, setBackendBaseUrl } = mod.forTesting();

function getIpcMain() {
  assert.ok(electronRequired, "módulo sob teste nunca requeriu electron");
  return electronStub.ipcMain;
}

// ── Backend /auth/me fake: conta chamadas, permissões configuráveis ──
import http from "node:http";

let meHits = 0;
let mePermissions: string[] = [];
const fakeBackend = http.createServer((_req, res) => {
  meHits++;
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ permissions: mePermissions }));
});
// Não segura o event loop vivo (node:test aguarda drenar antes de sair).
fakeBackend.unref();

async function startFakeBackend(): Promise<string> {
  await new Promise<void>((resolve) => fakeBackend.listen(0, "127.0.0.1", resolve));
  const addr = fakeBackend.address();
  if (typeof addr === "object" && addr) return `http://127.0.0.1:${addr.port}`;
  throw new Error("fake backend não escutou");
}

test("sem permissão → checkAndThrow rejeita", async () => {
  const gate = createPermissionGate({ fetchPermissions: async () => ["user.read"] });
  await assert.rejects(
    () => gate.checkAndThrow("finance.export_pdf"),
    /Permission 'finance.export_pdf' required/
  );
  assert.equal(await gate.check("finance.export_pdf"), false);
});

test("com permissão → executa (check passa)", async () => {
  const gate = createPermissionGate({ fetchPermissions: async () => ["finance.export_pdf"] });
  await gate.checkAndThrow("finance.export_pdf"); // não deve lançar
  assert.equal(await gate.check("finance.export_pdf"), true);
});

test("admin.* concede tudo", async () => {
  const gate = createPermissionGate({ fetchPermissions: async () => ["admin.*"] });
  assert.equal(await gate.check("finance.export_pdf"), true);
  assert.equal(await gate.check("qualquer.coisa"), true);
});

test("módulo.* cobre permissão do recurso", async () => {
  const gate = createPermissionGate({ fetchPermissions: async () => ["finance.*"] });
  assert.equal(await gate.check("finance.export_pdf"), true);
  assert.equal(await gate.check("user.create"), false);
});

test("cache: segunda chamada não bate no fetcher; expira após TTL", async () => {
  let calls = 0;
  const gate = createPermissionGate({
    fetchPermissions: async () => {
      calls++;
      return ["user.read"];
    },
    cacheTtlMs: 30,
  });

  await gate.check("user.read");
  await gate.check("user.read");
  await gate.check("user.read");
  assert.equal(calls, 1, "deve cachear dentro do TTL");

  await new Promise((r) => setTimeout(r, 50));
  await gate.check("user.read");
  assert.equal(calls, 2, "deve refetch após expirar o TTL");
});

test("sem token (fetcher devolve vazio) → fail-closed", async () => {
  const gate = createPermissionGate({ fetchPermissions: async () => [] });
  assert.equal(await gate.check("finance.export_pdf"), false);
});

// ── Handler-level (P0 3.6): registerProtectedHandler + /auth/me fake ──

test("handler protegido: deny → FORBIDDEN e não executa; allow → executa; cache e invalidação", async () => {
  const baseUrl = await startFakeBackend();
  setBackendBaseUrl(baseUrl);
  mod.registerTokenProvider(() => "tok-abc");

  let denyRan = false;
  mod.registerProtectedHandler("test:deny", "finance.export_pdf", async () => {
    denyRan = true;
    return { ok: true };
  });
  mod.registerProtectedHandler("test:allow", "finance.export_pdf", async () => ({ ok: true, n: 42 }));

  const handlers = getIpcMain().handlers;
  const denyFn = handlers.get("test:deny");
  const allowFn = handlers.get("test:allow");
  assert.ok(denyFn && allowFn, "handlers registrados no ipcMain");

  // 1) Sem permissão → rejeita, handler NÃO executa.
  mePermissions = [];
  meHits = 0;
  await assert.rejects(() => denyFn({}, {}), /finance\.export_pdf/);
  assert.equal(denyRan, false);
  assert.ok(meHits >= 1, "gate consultou /auth/me");

  // 2) Com permissão → executa normalmente.
  mePermissions = ["finance.export_pdf"];
  mod.clearPermissionCache();
  const result = (await allowFn({}, {})) as { ok: boolean; n: number };
  assert.equal(result.ok, true);
  assert.equal(result.n, 42);

  // 3) Cache: invocações seguintes dentro do TTL não batem no backend.
  const hitsAfterAllow = meHits;
  await allowFn({}, {});
  await allowFn({}, {});
  assert.equal(meHits, hitsAfterAllow, "cache evita refetch no TTL");

  // 4) admin.* concede qualquer handler.
  mePermissions = ["admin.*"];
  mod.clearPermissionCache();
  const denyResult = (await denyFn({}, {})) as { ok: boolean };
  assert.equal(denyResult.ok, true);
  assert.equal(denyRan, true);

  // 5) Invalidação explícita → próxima chamada bate no backend de novo.
  mePermissions = [];
  const hitsBefore = meHits;
  mod.clearPermissionCache();
  await assert.rejects(() => allowFn({}, {}));
  assert.ok(meHits > hitsBefore, "clearPermissionCache força refetch");

  fakeBackend.close();
  fakeBackend.closeAllConnections?.();
});

test("sem token registrado → fail-closed no handler", async () => {
  mod.clearPermissionCache(); // independe do cache do teste anterior
  mod.registerTokenProvider(null);
  mod.registerProtectedHandler("test:notoken", "finance.export_pdf", async () => ({ ran: true }));
  const fn = getIpcMain().handlers.get("test:notoken");
  assert.ok(fn);
  await assert.rejects(() => fn({}, {}), /finance\.export_pdf/);
});
