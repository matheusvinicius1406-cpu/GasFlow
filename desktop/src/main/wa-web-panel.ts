"use strict";
/**
 * WaWebPanel — protótipo híbrido (F0–F5): WhatsApp Web renderizado em
 * WebContentsView dentro da janela do GasFlow, APENAS para pairing, status
 * e visibilidade operacional. O envio continua 100% no Baileys.
 *
 * Regras do protótipo (respeitadas por construção):
 *  - NENHUMA automação de DOM: nenhum querySelector que clica, nenhum
 *    input sintético. O healthcheck faz apenas leitura de PRESENÇA de
 *    elementos-chave (canvas do QR, header, banner) — nunca de conteúdo.
 *  - NÃO usar <iframe>/<webview>/BrowserView: WebContentsView (Electron 30+).
 *  - Uma view por conta; partition persist:wa-web-<accountId> distinta por
 *    conta (duas contas coexistem; duas views da MESMA conta nunca são
 *    criadas — brigariam pelo socket).
 *  - Feature flag waWebPanel.enabled (default FALSE): com a flag off,
 *    nenhum WebContentsView é instanciado — código nem chega a criar view.
 *  - UA de Chrome estável PINADO (revisar trimestralmente — risco documentado).
 *  - Permissões: câmera/mic/geolocation/notificações NEGADAS por default
 *    (notificações ficam só no Baileys para evitar duplicação).
 *  - Sessão persistida pelo Electron em userData/Partitions/wa-web-<id> —
 *    path incluído no backup (docs/whatsapp-web-panel.md).
 *
 * Expectativa documentada ao usuário: Baileys (device #1) e a view (device
 * #2) são sessões independentes no telefone — ambas aparecem em
 * "Dispositivos conectados" e ambas recebem mensagens. Se o Baileys cair,
 * a view segue mostrando o estado real; se a view cair, o Baileys segue
 * enviando (perde-se visibilidade, não capacidade).
 */

import { app } from "electron";
import path from "node:path";
import { logger } from "./logger";

/** Chrome estável pinado — revisar a cada trimestre (risco: WA bloqueia UA). */
export const CHROME_USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36";

export const WA_WEB_URL = "https://web.whatsapp.com";

/** Contas suportadas — mesmos ids do serviço WhatsApp (wa-bridge). */
export const WA_WEB_ACCOUNTS = ["primary", "secondary"] as const;
export type WaWebAccountId = (typeof WA_WEB_ACCOUNTS)[number];

export type WaWebState = "closed" | "loading" | "connected" | "qr" | "disconnected" | "error";

export interface WaWebStatus {
  accountId: string;
  state: WaWebState;
  lastEventAt: string | null;
  lastError: string | null;
}

/** Superfície mínima usada do WebContentsView real (injetável p/ testes). */
export interface WaWebViewLike {
  webContents: {
    loadURL(url: string): Promise<void>;
    setUserAgent(ua: string): void;
    on(event: string, listener: (...args: unknown[]) => void): void;
    executeJavaScript(code: string): Promise<unknown>;
    reload(): void;
    isDestroyed(): boolean;
    session?: {
      setUserAgent?(ua: string): void;
      setPermissionRequestHandler?(handler: (_wc: unknown, permission: string, cb: (ok: boolean) => void) => void): void;
      clearStorageData?(options?: unknown): Promise<void>;
    } | null;
  };
  setBounds(bounds: { x: number; y: number; width: number; height: number }): void;
}

export interface WaWebPanelOptions {
  /** Intervalo do healthcheck visual (ms). Env WA_WEB_HEALTHCHECK_MS. */
  healthcheckMs?: number;
  /** Factory injetável — default cria WebContentsView real. */
  createView?: (opts: { partition: string; userAgent: string }) => WaWebViewLike;
  /** Hook: adiciona a view à janela (mainWindow.contentView.addChildView). */
  attachView?: (view: WaWebViewLike, accountId: string) => void;
  /** Hook: remove a view da janela antes de destruí-la. */
  detachView?: (view: WaWebViewLike, accountId: string) => void;
}

/** Script de presença (NÃO scraping): só booleans de elementos-chave. */
export const PRESENCE_SCRIPT = `
(() => {
  const q = (sel) => Boolean(document.querySelector(sel));
  return {
    qrPresent: q("canvas[aria-label]") || q("div[data-ref]"),
    chatHeaderPresent: q("header") || q("div[data-testid='chat-header']"),
    disconnectedBanner: q("div[data-testid='alert-disconnected']") || (document.body && document.body.innerText && document.body.innerText.indexOf("Telefone desconectado") !== -1),
    hasApp: q("#app") || q("#wa_web_initial_root"),
  };
})()
`;

function classify(probe: Record<string, unknown>): Exclude<WaWebState, "closed" | "loading" | "error"> {
  if (probe.qrPresent === true) return "qr";
  if (probe.disconnectedBanner === true) return "disconnected";
  if (probe.chatHeaderPresent === true) return "connected";
  return "disconnected";
}

export class WaWebPanel {
  private readonly views = new Map<string, WaWebViewLike>();
  private readonly statuses = new Map<string, WaWebStatus>();
  private activeAccountId: string | null = null;
  private healthTimer: NodeJS.Timeout | null = null;
  private readonly healthcheckMs: number;
  private readonly createView: (opts: { partition: string; userAgent: string }) => WaWebViewLike;
  private readonly attachView?: (view: WaWebViewLike, accountId: string) => void;
  private readonly detachView?: (view: WaWebViewLike, accountId: string) => void;
  /** Callback para push de status ao renderer (via main). */
  onStatus: ((status: WaWebStatus) => void) | null = null;

  constructor(options: WaWebPanelOptions = {}) {
    this.healthcheckMs = options.healthcheckMs ?? Number(process.env.WA_WEB_HEALTHCHECK_MS || 15_000);
    this.attachView = options.attachView;
    this.detachView = options.detachView;
    this.createView =
      options.createView ??
      ((opts) => {
        // Lazy require: evita tocar na classe real quando a flag está off.
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const { WebContentsView } = require("electron") as typeof import("electron");
        return new WebContentsView({
          webPreferences: {
            partition: opts.partition,
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
          },
        }) as unknown as WaWebViewLike;
      });
  }

  // ── Estado ──────────────────────────────────────────────

  getStatuses(): WaWebStatus[] {
    return WA_WEB_ACCOUNTS.map(
      (id) => this.statuses.get(id) ?? { accountId: id, state: "closed", lastEventAt: null, lastError: null },
    );
  }

  getStatus(accountId: string): WaWebStatus {
    return this.statuses.get(accountId) ?? { accountId, state: "closed", lastEventAt: null, lastError: null };
  }

  /** Número de views vivas — critério de aceite F5 (0 com flag off). */
  get viewCount(): number {
    return this.views.size;
  }

  private setStatus(accountId: string, patch: Partial<WaWebStatus>): void {
    const prev = this.getStatus(accountId);
    const next: WaWebStatus = {
      ...prev,
      ...patch,
      accountId,
      lastEventAt: new Date().toISOString(),
    };
    this.statuses.set(accountId, next);
    this.onStatus?.(next);
  }

  // ── Ciclo de vida das views ─────────────────────────────

  /** Cria (se necessário) e exibe a view da conta, na moldura informada. */
  async show(accountId: string, bounds?: { x: number; y: number; width: number; height: number }): Promise<void> {
    if (!(WA_WEB_ACCOUNTS as readonly string[]).includes(accountId)) {
      throw new Error(`Conta inválida: ${accountId}`);
    }
    let view = this.views.get(accountId);
    if (!view) {
      const partition = partitionFor(accountId);
      view = this.createView({ partition, userAgent: CHROME_USER_AGENT });
      view.webContents.setUserAgent(CHROME_USER_AGENT);
      try {
        view.webContents.session?.setUserAgent?.(CHROME_USER_AGENT);
      } catch { /* opcional */ }
      this.applyPermissionGuards(view);
      this.wireEvents(accountId, view);
      this.views.set(accountId, view);
      this.attachView?.(view, accountId);
      this.setStatus(accountId, { state: "loading", lastError: null });
      void view.webContents
        .loadURL(WA_WEB_URL)
        .catch((err: unknown) => {
          this.setStatus(accountId, { state: "error", lastError: String(err) });
        });
    }
    this.focusView(accountId, bounds);
  }

  /** Traz a view da conta para frente e aplica bounds da moldura React. */
  focusView(accountId: string, bounds?: { x: number; y: number; width: number; height: number }): void {
    const view = this.views.get(accountId);
    if (!view) return;
    this.activeAccountId = accountId;
    if (bounds) view.setBounds(bounds);
  }

  /** Esconde a view da tela (sem destruir a sessão). */
  hide(accountId: string): void {
    if (this.activeAccountId === accountId) this.activeAccountId = null;
    const view = this.views.get(accountId);
    if (view && !view.webContents.isDestroyed()) {
      view.setBounds({ x: 0, y: 0, width: 0, height: 0 });
    }
  }

  /** Aplica bounds da moldura (renderer manda o rect do placeholder). */
  setBounds(bounds: { x: number; y: number; width: number; height: number }): void {
    if (!this.activeAccountId) return;
    const view = this.views.get(this.activeAccountId);
    if (view && !view.webContents.isDestroyed()) view.setBounds(bounds);
  }

  /** Re-parear: destrói a view + limpa o storage da partition → QR novo. */
  async rePair(accountId: string): Promise<void> {
    const view = this.views.get(accountId);
    const session = view?.webContents.session;
    this.destroyView(accountId);
    if (session?.clearStorageData) {
      try {
        await session.clearStorageData({ storages: ["indexdb", "localstorage", "websql", "serviceworkers", "cachestorage"] });
      } catch (err) {
        logger.warn("wa-web-panel", `clearStorageData falhou: ${String(err)}`);
      }
    }
    this.setStatus(accountId, { state: "closed", lastError: null });
  }

  /** Fecha a view da conta (sessão persistida — reabrir não pede QR de novo). */
  close(accountId: string): void {
    this.destroyView(accountId);
    this.setStatus(accountId, { state: "closed" });
  }

  closeAll(): void {
    for (const id of Array.from(this.views.keys())) this.close(id);
    this.stopHealthcheck();
  }

  private destroyView(accountId: string): void {
    const view = this.views.get(accountId);
    if (!view) return;
    this.views.delete(accountId);
    if (this.activeAccountId === accountId) this.activeAccountId = null;
    try {
      this.detachView?.(view, accountId);
    } catch { /* janela pode já estar fechada */ }
    try {
      if (!view.webContents.isDestroyed()) {
        // Fecha o webContents; a sessão persist: continua em disco.
        (view.webContents as unknown as { destroy?: () => void }).destroy?.();
      }
    } catch { /* já destruída */ }
  }

  // ── Eventos do webContents (status bridge F3) ───────────

  private wireEvents(accountId: string, view: WaWebViewLike): void {
    const wc = view.webContents;
    wc.on("did-finish-load", () => {
      this.setStatus(accountId, { state: "loading" });
      void this.runHealthCheck(accountId);
    });
    wc.on("did-fail-load", (...args: unknown[]) => {
      // Assinatura Electron: (event, errorCode, errorDescription, validatedURL, isMainFrame)
      const description = typeof args[2] === "string" && args[2] ? args[2] : "load failed";
      this.setStatus(accountId, { state: "error", lastError: description });
    });
    wc.on("did-navigate", () => {
      this.setStatus(accountId, { state: "loading" });
    });
    wc.on("page-title-updated", () => {
      // Título muda (ex.: "(n) WhatsApp") — toca o timestamp do último evento.
      this.setStatus(accountId, {});
    });
  }

  /**
   * Healthcheck visual (F3): lê PRESENÇA de elementos-chave e classifica.
   * Roda no intervalo e sob demanda após did-finish-load. Sem scraping de
   * conteúdo — o script só devolve booleans.
   */
  async runHealthCheck(accountId: string): Promise<void> {
    const view = this.views.get(accountId);
    if (!view || view.webContents.isDestroyed()) return;
    try {
      const probe = (await view.webContents.executeJavaScript(PRESENCE_SCRIPT)) as Record<string, unknown> | null;
      if (probe && typeof probe === "object") {
        const state = classify(probe);
        this.setStatus(accountId, { state });
      }
    } catch {
      // Página em navegação/CSP — não é erro do painel; mantém estado.
    }
  }

  startHealthcheck(): void {
    if (this.healthTimer) return;
    this.healthTimer = setInterval(() => {
      for (const id of this.views.keys()) void this.runHealthCheck(id);
    }, this.healthcheckMs);
    this.healthTimer.unref?.();
  }

  stopHealthcheck(): void {
    if (this.healthTimer) {
      clearInterval(this.healthTimer);
      this.healthTimer = null;
    }
  }

  // ── Permissões (negar por default) ──────────────────────

  private applyPermissionGuards(view: WaWebViewLike): void {
    const session = view.webContents.session;
    if (!session?.setPermissionRequestHandler) return;
    // Tudo negado, incluindo notificações — default do protótipo é
    // "notificações só no Baileys" (evita duplicação entre devices).
    session.setPermissionRequestHandler((_wc, permission, callback) => {
      callback(false);
      logger.info("wa-web-panel", `permissão negada: ${permission}`);
    });
  }
}

// ── Helpers ───────────────────────────────────────────────

export interface WaWebPanelSettings {
  /** Feature flag do protótipo. Default: { enabled: false } (config.ts). */
  waWebPanel?: { enabled?: boolean };
}

/**
 * F5 — única porta de entrada do painel: com a flag off, devolve null e
 * NENHUM WebContentsView é instanciado (critério: webContents.getAllWebContents()
 * não ganha novas views). Com a flag on, o painel já nasce com o healthcheck.
 */
export function createPanelIfEnabled(
  settings: WaWebPanelSettings,
  options: WaWebPanelOptions = {},
): WaWebPanel | null {
  if (settings.waWebPanel?.enabled !== true) {
    logger.info("wa-web-panel", "flag desligada — painel não instanciado");
    return null;
  }
  const panel = new WaWebPanel(options);
  panel.startHealthcheck();
  return panel;
}

export function partitionFor(accountId: string): string {
  return `persist:wa-web-${accountId}`;
}

/** Path em disco da sessão da conta — incluir no backup (F4). */
export function partitionPath(accountId: string): string {
  return path.join(app.getPath("userData"), "Partitions", `wa-web-${accountId}`);
}
