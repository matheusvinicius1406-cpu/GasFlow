/**
 * Testes da máquina de estados do auto-update (dist/main/updater.js).
 * Usa autoUpdater falso (EventEmitter) e stubs de electron/electron-updater —
 * roda em node puro, sem GUI.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import Module from "node:module";
import { createRequire } from "node:module";

// Stubs instalados ANTES do primeiro require do módulo sob teste.
const origRequire = Module.prototype.require;
Module.prototype.require = function (this: unknown, id: string) {
  if (id === "electron") {
    return {
      app: { isPackaged: false },
      BrowserWindow: { getAllWindows: () => [] },
      ipcMain: { handle: () => undefined },
    };
  }
  if (id === "electron-updater") {
    return { autoUpdater: new EventEmitter() };
  }
  return origRequire.apply(this, arguments as unknown as Parameters<typeof origRequire>);
};

const req = createRequire(__filename);
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { createUpdateState } = req("../dist/main/updater.js") as {
  createUpdateState: (deps?: { log?: (...a: unknown[]) => void }) => {
    get: () => { status: string; version: string | null; progress: number; error: string | null };
    set: (patch: Record<string, unknown>) => unknown;
    subscribe: (fn: (s: unknown) => void) => () => boolean;
    wire: (au: EventEmitter) => void;
  };
};

function makeFakeAutoUpdater() {
  const emitter = new EventEmitter();
  return emitter;
}

test("estado inicial é idle", () => {
  const st = createUpdateState();
  assert.equal(st.get().status, "idle");
  assert.equal(st.get().version, null);
  assert.equal(st.get().progress, 0);
  assert.equal(st.get().error, null);
});

test("fluxo completo: idle → checking → available → downloading → ready", () => {
  const st = createUpdateState();
  const au = makeFakeAutoUpdater();
  st.wire(au);

  au.emit("checking-for-update");
  assert.equal(st.get().status, "checking");

  au.emit("update-available", { version: "1.2.0" });
  assert.equal(st.get().status, "available");
  assert.equal(st.get().version, "1.2.0");
  assert.equal(st.get().error, null);

  au.emit("download-progress", { percent: 55.4 });
  assert.equal(st.get().status, "downloading");
  assert.equal(st.get().progress, 55);

  au.emit("update-downloaded", { version: "1.2.0" });
  assert.equal(st.get().status, "ready");
  assert.equal(st.get().progress, 100);
  assert.equal(st.get().version, "1.2.0");
});

test("erro do autoUpdater vira status error com mensagem", () => {
  const st = createUpdateState();
  const au = makeFakeAutoUpdater();
  st.wire(au);
  au.emit("error", new Error("net offline"));
  assert.equal(st.get().status, "error");
  assert.equal(st.get().error, "net offline");
});

test("update-not-available vira up-to-date", () => {
  const st = createUpdateState();
  const au = makeFakeAutoUpdater();
  st.wire(au);
  au.emit("update-not-available", { version: "1.1.1" });
  assert.equal(st.get().status, "up-to-date");
  assert.equal(st.get().version, "1.1.1");
});

test("subscribe recebe mudanças e unsubscribe para as notificações", () => {
  const st = createUpdateState();
  const seen: string[] = [];
  const off = st.subscribe((s) => seen.push((s as { status: string }).status));
  st.set({ status: "checking" });
  st.set({ status: "available" });
  off();
  st.set({ status: "error" });
  assert.deepEqual(seen, ["checking", "available"]);
});

test("listener que lança não derruba o set()", () => {
  const st = createUpdateState();
  st.subscribe(() => {
    throw new Error("listener quebrado");
  });
  const s = st.set({ status: "checking" });
  assert.equal(s.status, "checking");
});

// ── registerUpdateIpc idempotência + setupAutoUpdate guard (B4) ──

test("registerUpdateIpc é idempotente: segunda chamada não duplica handlers", () => {
  const handled: string[] = [];
  Module.prototype.require = function (this: unknown, id: string) {
    if (id === "electron") {
      return {
        app: { isPackaged: false },
        BrowserWindow: { getAllWindows: () => [] },
        ipcMain: {
          handle: (channel: string) => {
            handled.push(channel);
          },
        },
      };
    }
    if (id === "electron-updater") {
      return { autoUpdater: new EventEmitter() };
    }
    return origRequire.apply(this, arguments as unknown as Parameters<typeof origRequire>);
  };
  // Limpa o cache: o updater.js do topo do arquivo usou outro stub de ipcMain.
  const updaterPath = req.resolve("../dist/main/updater.js");
  delete req.cache[updaterPath];
  const fresh = req("../dist/main/updater.js") as { registerUpdateIpc: () => void };
  fresh.registerUpdateIpc();
  const firstCount = handled.length;
  assert.ok(firstCount >= 3, "pelo menos update:check/install/state registrados");
  fresh.registerUpdateIpc(); // segunda chamada — deve ser no-op
  assert.equal(handled.length, firstCount, "segunda chamada não deve registrar de novo");
  // Restaura o stub original do topo para os próximos testes.
  Module.prototype.require = origRequire;
  delete req.cache[updaterPath];
});

test("setupAutoUpdate: app não empacotado (dev) não configura nada", () => {
  Module.prototype.require = function (this: unknown, id: string) {
    if (id === "electron") {
      return {
        app: { isPackaged: false },
        BrowserWindow: { getAllWindows: () => [] },
        ipcMain: { handle: () => undefined },
      };
    }
    if (id === "electron-updater") {
      return { autoUpdater: new EventEmitter() };
    }
    return origRequire.apply(this, arguments as unknown as Parameters<typeof origRequire>);
  };
  const fresh = req("../dist/main/updater.js") as {
    setupAutoUpdate: (getChannel?: () => string) => void;
  };
  // Em dev (isPackaged=false), setupAutoUpdate deve retornar sem lançar.
  // Não há como assertar "não fez nada" diretamente, mas não lançar já
  // cobre o guard (sem ele, autoUpdater.checkForUpdatesAndNotify explodiria).
  fresh.setupAutoUpdate(() => "beta");
});
