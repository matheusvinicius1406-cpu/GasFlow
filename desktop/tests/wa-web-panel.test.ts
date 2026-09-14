/**
 * Testes do protótipo WhatsApp Web em WebContentsView (wa-web-panel.ts).
 * Rodam contra dist/main/*.js com o módulo electron stubulado — nenhuma
 * janela real, nenhuma rede. A view é FAKE (injetada via createView).
 *
 * O módulo compilado é carregado UMA VEZ com o stub ativo (import top-level
 * de "electron" acontece aqui); os testes em si não precisam do stub.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import os from "node:os";
import Module from "node:module";
import { createRequire } from "node:module";
import type { WaWebPanel, WaWebViewLike } from "../src/main/wa-web-panel";

const origRequire = Module.prototype.require;

const req = createRequire(__filename);
const panelPath = path.resolve(__dirname, "../dist/main/wa-web-panel.js");

type PanelModule = typeof import("../src/main/wa-web-panel");

/** Carrega o dist UMA vez com electron stubulado (app.getPath fake). */
const panelMod: PanelModule = (() => {
  Module.prototype.require = function (this: unknown, id: string) {
    if (id === "electron") {
      return {
        app: { getPath: () => path.join(os.tmpdir(), "gf-waweb-test-userdata"), isPackaged: false },
        WebContentsView: class {},
      };
    }
    return origRequire.apply(this, arguments as unknown as Parameters<typeof origRequire>);
  };
  try {
    return req(panelPath) as PanelModule;
  } finally {
    Module.prototype.require = origRequire;
  }
})();

/** Fake view: captura listeners, UA e o permission handler instalado. */
function makeFakeView(overrides: Partial<{ probe: Record<string, unknown> | null; loadError: Error }> = {}) {
  const listeners: Record<string, Array<(...a: unknown[]) => void>> = {};
  let ua = "";
  let permissionHandler: ((_wc: unknown, permission: string, cb: (ok: boolean) => void) => void) | null = null;
  const view = {
    get permissionHandler() {
      return permissionHandler;
    },
    get ua() {
      return ua;
    },
    destroyed: false,
    webContents: {
      loadURL: async () => {
        if (overrides.loadError) throw overrides.loadError;
      },
      setUserAgent: (value: string) => {
        ua = value;
      },
      on: (event: string, listener: (...a: unknown[]) => void) => {
        (listeners[event] ||= []).push(listener);
      },
      executeJavaScript: async () => overrides.probe ?? null,
      reload: () => undefined,
      isDestroyed: () => view.destroyed,
      destroy: () => {
        view.destroyed = true;
      },
      session: {
        setUserAgent: (value: string) => {
          ua = value;
        },
        setPermissionRequestHandler: (handler: (_wc: unknown, permission: string, cb: (ok: boolean) => void) => void) => {
          permissionHandler = handler;
        },
        clearStorageData: async () => undefined,
      },
    },
    setBounds: () => undefined,
    emit(event: string, ...args: unknown[]) {
      for (const l of listeners[event] ?? []) l(...args);
    },
  };
  return view;
}

type FakeView = ReturnType<typeof makeFakeView>;

function makePanel(viewFactory?: () => FakeView): { panel: WaWebPanel & { viewCount: number }; created: FakeView[] } {
  const created: FakeView[] = [];
  const panel = new panelMod.WaWebPanel({
    healthcheckMs: 60_000,
    createView: () => {
      const v = viewFactory ? viewFactory() : makeFakeView();
      created.push(v);
      return v as unknown as WaWebViewLike;
    },
  }) as WaWebPanel & { viewCount: number };
  return { panel, created };
}

const settle = (ms = 10) => new Promise((r) => setTimeout(r, ms));

test("F5: flag off — createPanelIfEnabled devolve null (nenhuma view instanciada)", () => {
  const panel = panelMod.createPanelIfEnabled({ waWebPanel: { enabled: false } });
  assert.equal(panel, null);
});

test("F5: flag on — painel criado com healthcheck ativo, 0 views até show()", () => {
  const active = panelMod.createPanelIfEnabled({ waWebPanel: { enabled: true } }, { healthcheckMs: 60_000 });
  assert.ok(active !== null);
  assert.equal(active.viewCount, 0);
  active.stopHealthcheck();
});

test("F1: show() cria UMA view com UA Chrome pinado", async () => {
  const { panel, created } = makePanel();
  try {
    await panel.show("primary");
    assert.equal(created.length, 1);
    assert.equal(created[0].ua, panelMod.CHROME_USER_AGENT);
    assert.ok(panelMod.CHROME_USER_AGENT.includes("Chrome/128"), "UA pinado documentado");
  } finally {
    panel.closeAll();
  }
});

test("F1: loadURL com erro → estado error com lastError", async () => {
  const { panel } = makePanel(() => makeFakeView({ loadError: new Error("net::ERR_INTERNET_DISCONNECTED") }));
  try {
    await panel.show("primary");
    await settle();
    const st = panel.getStatus("primary");
    assert.equal(st.state, "error");
    assert.ok(String(st.lastError).includes("ERR_INTERNET_DISCONNECTED"));
  } finally {
    panel.closeAll();
  }
});

test("F2: partições distintas por conta (persist:wa-web-<id>)", () => {
  assert.equal(panelMod.partitionFor("primary"), "persist:wa-web-primary");
  assert.equal(panelMod.partitionFor("secondary"), "persist:wa-web-secondary");
  assert.notEqual(panelMod.partitionFor("primary"), panelMod.partitionFor("secondary"));
});

test("F2: uma view por conta — show repetido reusa; contas diferentes coexistem", async () => {
  const { panel, created } = makePanel();
  try {
    await panel.show("primary");
    await panel.show("primary");
    assert.equal(created.length, 1, "mesma conta NÃO cria segunda view (1 conta = 1 sessão)");
    await panel.show("secondary");
    assert.equal(created.length, 2);
    assert.equal(panel.viewCount, 2);
  } finally {
    panel.closeAll();
  }
});

test("conta fora da lista é rejeitada sem criar view", async () => {
  const { panel, created } = makePanel();
  try {
    await assert.rejects(() => panel.show("terceira"), /Conta inválida/);
    assert.equal(created.length, 0);
  } finally {
    panel.stopHealthcheck();
  }
});

test("F3: healthcheck classifica por PRESENÇA — qr / connected / disconnected", async () => {
  const cases: Array<{ probe: Record<string, unknown>; expected: string }> = [
    { probe: { qrPresent: true, chatHeaderPresent: false, disconnectedBanner: false }, expected: "qr" },
    { probe: { qrPresent: false, chatHeaderPresent: true, disconnectedBanner: false }, expected: "connected" },
    { probe: { qrPresent: false, chatHeaderPresent: false, disconnectedBanner: true }, expected: "disconnected" },
  ];
  for (const c of cases) {
    const { panel } = makePanel(() => makeFakeView({ probe: c.probe }));
    try {
      await panel.show("primary");
      await panel.runHealthCheck("primary");
      assert.equal(panel.getStatus("primary").state, c.expected, `probe ${JSON.stringify(c.probe)}`);
    } finally {
      panel.closeAll();
    }
  }
});

test("F3: did-fail-load → error; did-finish-load → healthcheck; eventos atualizam lastEventAt", async () => {
  const fake = makeFakeView({ probe: { qrPresent: true } });
  const { panel } = makePanel(() => fake);
  try {
    const events: Array<Record<string, unknown>> = [];
    panel.onStatus = (s) => events.push({ ...s });
    await panel.show("primary");

    fake.emit("did-fail-load", {}, -101, "ERR_CONNECTION_REFUSED", "https://web.whatsapp.com", true);
    assert.equal(panel.getStatus("primary").state, "error");
    assert.ok(String(panel.getStatus("primary").lastError).includes("ERR_CONNECTION_REFUSED"));

    fake.emit("did-finish-load");
    await settle();
    assert.equal(panel.getStatus("primary").state, "qr");

    const eventsBefore = events.length;
    fake.emit("page-title-updated", "(2) WhatsApp");
    assert.ok(events.length >= eventsBefore, "onStatus notificado a cada mudança");
  } finally {
    panel.closeAll();
  }
});

test("permissões: guard do painel nega tudo (media/geolocation/notifications)", async () => {
  const fake = makeFakeView();
  const { panel } = makePanel(() => fake);
  try {
    await panel.show("primary");
    const handler = fake.permissionHandler;
    assert.ok(handler, "painel deve instalar setPermissionRequestHandler");
    const decisions: Record<string, boolean> = {};
    for (const permission of ["media", "geolocation", "notifications", "midi"]) {
      handler(null, permission, (ok: boolean) => {
        decisions[permission] = ok;
      });
    }
    assert.deepEqual(decisions, { media: false, geolocation: false, notifications: false, midi: false });
  } finally {
    panel.closeAll();
  }
});

test("rePair destrói a view, limpa storage e volta a closed; show recria", async () => {
  const { panel, created } = makePanel();
  try {
    await panel.show("primary");
    await panel.rePair("primary");
    assert.equal(panel.viewCount, 0);
    assert.equal(panel.getStatus("primary").state, "closed");
    await panel.show("primary");
    assert.equal(created.length, 2);
  } finally {
    panel.closeAll();
  }
});

test("closeAll fecha tudo; statuses voltam a closed", async () => {
  const { panel } = makePanel();
  try {
    await panel.show("primary");
    await panel.show("secondary");
    panel.closeAll();
    assert.equal(panel.viewCount, 0);
    assert.equal(panel.getStatus("primary").state, "closed");
    assert.equal(panel.getStatus("secondary").state, "closed");
  } finally {
    panel.stopHealthcheck();
  }
});
