/**
 * Testes do IPC do auto-update (dist/main/updater.js): o que o renderer
 * recebe nos canais update:check / update:install / update:state.
 * A máquina de estados em si já é coberta em updater.test.ts; aqui vale o
 * contrato da barreira IPC (retorno { ok, ... }, idempotência do registro e
 * propagação de erro do electron-updater).
 * Stubs de electron/electron-updater instalados ANTES do require.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import Module from "node:module";
import { createRequire } from "node:module";

type Handler = (event: unknown, ...args: unknown[]) => unknown | Promise<unknown>;

const handlers = new Map<string, Handler>();
let checkResult: { fail?: string } = {};
let installResult: { fail?: string } = {};
const installCalls: unknown[] = [];
const checkCalls: unknown[] = [];

const fakeAutoUpdater = Object.assign(new EventEmitter(), {
  checkForUpdates: async () => {
    checkCalls.push(true);
    if (checkResult.fail) throw new Error(checkResult.fail);
  },
  quitAndInstall: (...args: unknown[]) => {
    installCalls.push(args);
    if (installResult.fail) throw new Error(installResult.fail);
  },
  checkForUpdatesAndNotify: async () => undefined,
});

const electronStub = {
  app: { isPackaged: false },
  BrowserWindow: { getAllWindows: () => [] },
  ipcMain: {
    handle: (channel: string, handler: Handler) => {
      if (handlers.has(channel)) throw new Error(`handler duplicado: ${channel}`);
      handlers.set(channel, handler);
    },
  },
};

const origRequire = Module.prototype.require;
Module.prototype.require = function (this: unknown, id: string) {
  if (id === "electron") return electronStub;
  if (id === "electron-updater") return { autoUpdater: fakeAutoUpdater };
  return origRequire.apply(this, arguments as unknown as Parameters<typeof origRequire>);
};

const req = createRequire(__filename);
const { registerUpdateIpc } = req("../dist/main/updater.js") as {
  registerUpdateIpc: () => void;
};

async function invoke(channel: string, ...args: unknown[]) {
  const handler = handlers.get(channel);
  assert.ok(handler, `handler ${channel} deve existir`);
  return handler({}, ...args);
}

test("registerUpdateIpc registra os 3 canais que o preload expõe", () => {
  registerUpdateIpc();
  assert.deepEqual([...handlers.keys()].sort(), ["update:check", "update:install", "update:state"]);
});

test("registerUpdateIpc é idempotente (segunda chamada não duplica nem lança)", () => {
  registerUpdateIpc();
  registerUpdateIpc();
  assert.equal(handlers.size, 3);
});

test("update:state devolve o estado inicial completo", async () => {
  const state = (await invoke("update:state")) as Record<string, unknown>;
  assert.equal(state.status, "idle");
  assert.equal(state.version, null);
  assert.equal(state.progress, 0);
  assert.equal(state.error, null);
});

test("update:check devolve { ok:true, state } quando o electron-updater responde", async () => {
  checkResult = {};
  const res = (await invoke("update:check")) as { ok: boolean; state: Record<string, unknown> };
  assert.equal(res.ok, true);
  assert.equal(typeof res.state, "object");
  assert.equal(checkCalls.length, 1, "deve chamar autoUpdater.checkForUpdates");
});

test("update:check converte erro do updater em { ok:false, error } (não lança p/ renderer)", async () => {
  checkResult = { fail: "net offline" };
  const res = (await invoke("update:check")) as { ok: boolean; error: string };
  assert.deepEqual(res, { ok: false, error: "net offline" });
  checkResult = {};
});

test("update:install chama quitAndInstall(false, true) e responde { ok:true }", async () => {
  installResult = {};
  const before = installCalls.length;
  const res = (await invoke("update:install")) as { ok: boolean };
  assert.deepEqual(res, { ok: true });
  assert.equal(installCalls.length, before + 1);
  assert.deepEqual(installCalls[installCalls.length - 1], [false, true]);
});

test("update:install propaga falha como { ok:false, error }", async () => {
  installResult = { fail: "sem permissão" };
  const res = (await invoke("update:install")) as { ok: boolean; error: string };
  assert.deepEqual(res, { ok: false, error: "sem permissão" });
  installResult = {};
});
