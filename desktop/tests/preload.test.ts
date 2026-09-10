/**
 * Testes do preload (dist/preload/index.js): window.gasflow e window.gasflowUpdater
 * expostos via contextBridge — com electron stubulado.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import Module from "node:module";
import { createRequire } from "node:module";

const origRequire = Module.prototype.require;

const exposed: Record<string, unknown> = {};
const registered: { channel: string; cb: (...a: unknown[]) => void }[] = [];

Module.prototype.require = function (this: unknown, id: string) {
  if (id === "electron") {
    return {
      contextBridge: {
        exposeInMainWorld: (key: string, api: unknown) => {
          exposed[key] = api;
        },
      },
      ipcRenderer: {
        invoke: (channel: string) => {
          registered.push({ channel, cb: () => undefined });
          return Promise.resolve({ channel });
        },
        on: (channel: string, cb: (...a: unknown[]) => void) => {
          registered.push({ channel, cb });
        },
        removeListener: () => undefined,
      },
    };
  }
  return origRequire.apply(this, arguments as unknown as Parameters<typeof origRequire>);
};

const req = createRequire(__filename);
// eslint-disable-next-line @typescript-eslint/no-var-requires
req(path.resolve(__dirname, "../dist/preload/index.js"));

test("contextBridge expõe window.gasflow com a API esperada", () => {
  const api = exposed["gasflow"] as Record<string, () => unknown> | undefined;
  assert.ok(api, "window.gasflow deve existir");
  for (const fn of [
    "getSettings",
    "saveSettings",
    "agentStart",
    "agentStop",
    "waStart",
    "waStop",
    "waGetQr",
    "listConversations",
    "onLog",
  ]) {
    assert.equal(typeof api?.[fn], "function", `gasflow.${fn} deve ser função`);
  }
});

test("contextBridge expõe window.gasflowUpdater (check/install/getState/onStateChange)", () => {
  const api = exposed["gasflowUpdater"] as Record<string, () => unknown> | undefined;
  assert.ok(api, "window.gasflowUpdater deve existir");
  assert.equal(typeof api?.check, "function");
  assert.equal(typeof api?.install, "function");
  assert.equal(typeof api?.getState, "function");
  assert.equal(typeof api?.onStateChange, "function");
});

test("onLog registra listener em gasflow:log e devolve unsubscribe", () => {
  const api = exposed["gasflow"] as { onLog: (cb: () => void) => () => void };
  const before = registered.length;
  const off = api.onLog(() => undefined);
  assert.equal(registered.length, before + 1);
  assert.equal(registered[registered.length - 1].channel, "gasflow:log");
  assert.equal(typeof off, "function");
});
