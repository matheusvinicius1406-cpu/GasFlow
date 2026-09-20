"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.WaWebPanel = exports.PRESENCE_SCRIPT = exports.WA_WEB_ACCOUNTS = exports.WA_WEB_URL = exports.CHROME_USER_AGENT = void 0;
exports.createPanelIfEnabled = createPanelIfEnabled;
exports.partitionFor = partitionFor;
exports.partitionPath = partitionPath;
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
const electron_1 = require("electron");
const node_path_1 = __importDefault(require("node:path"));
const logger_1 = require("./logger");
/** Chrome estável pinado — revisar a cada trimestre (risco: WA bloqueia UA). */
exports.CHROME_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36";
exports.WA_WEB_URL = "https://web.whatsapp.com";
/** Contas suportadas — mesmos ids do serviço WhatsApp (wa-bridge). */
exports.WA_WEB_ACCOUNTS = ["primary", "secondary"];
/** Script de presença (NÃO scraping): só booleans de elementos-chave. */
exports.PRESENCE_SCRIPT = `
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
function classify(probe) {
    if (probe.qrPresent === true)
        return "qr";
    if (probe.disconnectedBanner === true)
        return "disconnected";
    if (probe.chatHeaderPresent === true)
        return "connected";
    return "disconnected";
}
class WaWebPanel {
    views = new Map();
    statuses = new Map();
    activeAccountId = null;
    healthTimer = null;
    healthcheckMs;
    createView;
    attachView;
    detachView;
    /** Callback para push de status ao renderer (via main). */
    onStatus = null;
    constructor(options = {}) {
        this.healthcheckMs = options.healthcheckMs ?? Number(process.env.WA_WEB_HEALTHCHECK_MS || 15_000);
        this.attachView = options.attachView;
        this.detachView = options.detachView;
        this.createView =
            options.createView ??
                ((opts) => {
                    // Lazy require: evita tocar na classe real quando a flag está off.
                    // eslint-disable-next-line @typescript-eslint/no-var-requires
                    const { WebContentsView } = require("electron");
                    return new WebContentsView({
                        webPreferences: {
                            partition: opts.partition,
                            nodeIntegration: false,
                            contextIsolation: true,
                            sandbox: true,
                        },
                    });
                });
    }
    // ── Estado ──────────────────────────────────────────────
    getStatuses() {
        return exports.WA_WEB_ACCOUNTS.map((id) => this.statuses.get(id) ?? { accountId: id, state: "closed", lastEventAt: null, lastError: null });
    }
    getStatus(accountId) {
        return this.statuses.get(accountId) ?? { accountId, state: "closed", lastEventAt: null, lastError: null };
    }
    /** Número de views vivas — critério de aceite F5 (0 com flag off). */
    get viewCount() {
        return this.views.size;
    }
    setStatus(accountId, patch) {
        const prev = this.getStatus(accountId);
        const next = {
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
    async show(accountId, bounds) {
        if (!exports.WA_WEB_ACCOUNTS.includes(accountId)) {
            throw new Error(`Conta inválida: ${accountId}`);
        }
        let view = this.views.get(accountId);
        if (!view) {
            const partition = partitionFor(accountId);
            view = this.createView({ partition, userAgent: exports.CHROME_USER_AGENT });
            view.webContents.setUserAgent(exports.CHROME_USER_AGENT);
            try {
                view.webContents.session?.setUserAgent?.(exports.CHROME_USER_AGENT);
            }
            catch { /* opcional */ }
            this.applyPermissionGuards(view);
            this.wireEvents(accountId, view);
            this.views.set(accountId, view);
            this.attachView?.(view, accountId);
            this.setStatus(accountId, { state: "loading", lastError: null });
            void view.webContents
                .loadURL(exports.WA_WEB_URL)
                .catch((err) => {
                this.setStatus(accountId, { state: "error", lastError: String(err) });
            });
        }
        this.focusView(accountId, bounds);
    }
    /** Traz a view da conta para frente e aplica bounds da moldura React. */
    focusView(accountId, bounds) {
        const view = this.views.get(accountId);
        if (!view)
            return;
        this.activeAccountId = accountId;
        if (bounds)
            view.setBounds(bounds);
    }
    /** Esconde a view da tela (sem destruir a sessão). */
    hide(accountId) {
        if (this.activeAccountId === accountId)
            this.activeAccountId = null;
        const view = this.views.get(accountId);
        if (view && !view.webContents.isDestroyed()) {
            view.setBounds({ x: 0, y: 0, width: 0, height: 0 });
        }
    }
    /** Aplica bounds da moldura (renderer manda o rect do placeholder). */
    setBounds(bounds) {
        if (!this.activeAccountId)
            return;
        const view = this.views.get(this.activeAccountId);
        if (view && !view.webContents.isDestroyed())
            view.setBounds(bounds);
    }
    /** Re-parear: destrói a view + limpa o storage da partition → QR novo. */
    async rePair(accountId) {
        const view = this.views.get(accountId);
        const session = view?.webContents.session;
        this.destroyView(accountId);
        if (session?.clearStorageData) {
            try {
                await session.clearStorageData({ storages: ["indexdb", "localstorage", "websql", "serviceworkers", "cachestorage"] });
            }
            catch (err) {
                logger_1.logger.warn("wa-web-panel", `clearStorageData falhou: ${String(err)}`);
            }
        }
        this.setStatus(accountId, { state: "closed", lastError: null });
    }
    /** Fecha a view da conta (sessão persistida — reabrir não pede QR de novo). */
    close(accountId) {
        this.destroyView(accountId);
        this.setStatus(accountId, { state: "closed" });
    }
    closeAll() {
        for (const id of Array.from(this.views.keys()))
            this.close(id);
        this.stopHealthcheck();
    }
    destroyView(accountId) {
        const view = this.views.get(accountId);
        if (!view)
            return;
        this.views.delete(accountId);
        if (this.activeAccountId === accountId)
            this.activeAccountId = null;
        try {
            this.detachView?.(view, accountId);
        }
        catch { /* janela pode já estar fechada */ }
        try {
            if (!view.webContents.isDestroyed()) {
                // Fecha o webContents; a sessão persist: continua em disco.
                view.webContents.destroy?.();
            }
        }
        catch { /* já destruída */ }
    }
    // ── Eventos do webContents (status bridge F3) ───────────
    wireEvents(accountId, view) {
        const wc = view.webContents;
        wc.on("did-finish-load", () => {
            this.setStatus(accountId, { state: "loading" });
            void this.runHealthCheck(accountId);
        });
        wc.on("did-fail-load", (...args) => {
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
    async runHealthCheck(accountId) {
        const view = this.views.get(accountId);
        if (!view || view.webContents.isDestroyed())
            return;
        try {
            const probe = (await view.webContents.executeJavaScript(exports.PRESENCE_SCRIPT));
            if (probe && typeof probe === "object") {
                const state = classify(probe);
                this.setStatus(accountId, { state });
            }
        }
        catch {
            // Página em navegação/CSP — não é erro do painel; mantém estado.
        }
    }
    startHealthcheck() {
        if (this.healthTimer)
            return;
        this.healthTimer = setInterval(() => {
            for (const id of this.views.keys())
                void this.runHealthCheck(id);
        }, this.healthcheckMs);
        this.healthTimer.unref?.();
    }
    stopHealthcheck() {
        if (this.healthTimer) {
            clearInterval(this.healthTimer);
            this.healthTimer = null;
        }
    }
    // ── Permissões (negar por default) ──────────────────────
    applyPermissionGuards(view) {
        const session = view.webContents.session;
        if (!session?.setPermissionRequestHandler)
            return;
        // Tudo negado, incluindo notificações — default do protótipo é
        // "notificações só no Baileys" (evita duplicação entre devices).
        session.setPermissionRequestHandler((_wc, permission, callback) => {
            callback(false);
            logger_1.logger.info("wa-web-panel", `permissão negada: ${permission}`);
        });
    }
}
exports.WaWebPanel = WaWebPanel;
/**
 * F5 — única porta de entrada do painel: com a flag off, devolve null e
 * NENHUM WebContentsView é instanciado (critério: webContents.getAllWebContents()
 * não ganha novas views). Com a flag on, o painel já nasce com o healthcheck.
 */
function createPanelIfEnabled(settings, options = {}) {
    if (settings.waWebPanel?.enabled !== true) {
        logger_1.logger.info("wa-web-panel", "flag desligada — painel não instanciado");
        return null;
    }
    const panel = new WaWebPanel(options);
    panel.startHealthcheck();
    return panel;
}
function partitionFor(accountId) {
    return `persist:wa-web-${accountId}`;
}
/** Path em disco da sessão da conta — incluir no backup (F4). */
function partitionPath(accountId) {
    return node_path_1.default.join(electron_1.app.getPath("userData"), "Partitions", `wa-web-${accountId}`);
}
//# sourceMappingURL=wa-web-panel.js.map