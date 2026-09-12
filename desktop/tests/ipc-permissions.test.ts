/**
 * Testes do gate de permissão IPC (dist/main/ipc-permissions.js).
 * Node puro (node:test) — sem Electron; o fetcher é injetado.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import Module from "node:module";
import { createRequire } from "node:module";

// Stub do electron ANTES do primeiro require do módulo sob teste.
const origRequire = Module.prototype.require;
Module.prototype.require = function (this: unknown, id: string) {
  if (id === "electron") {
    return { ipcMain: { handlers: new Map<string, Function>(), handle: function (ch: string, fn: Function) { this.handlers.set(ch, fn); } } };
  }
  return origRequire.apply(this, arguments as unknown as Parameters<typeof origRequire>);
};

const req = createRequire(__filename);
// eslint-disable-next-line @typescript-eslint/no-var-requires
const mod = req("../dist/main/ipc-permissions.js") as {
  forTesting: () => { createPermissionGate: (opts?: { fetchPermissions?: () => Promise<string[]>; cacheTtlMs?: number }) => {
    check: (p: string) => Promise<boolean>;
    checkAndThrow: (p: string) => Promise<void>;
    _debug: { stats: () => { cached: boolean } };
  } };
};

const { createPermissionGate } = mod.forTesting();

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
