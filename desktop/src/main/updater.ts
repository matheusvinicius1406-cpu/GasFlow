// @ts-nocheck
"use strict";
/**
 * Auto-update (electron-updater + GitHub Releases).
 *
 * Fluxo: push de tag v* → GitHub Actions builda e publica a release →
 * apps instalados detectam (15s após abrir, e a cada 6h), baixam e
 * instalam ao clicar em "Reiniciar e instalar" (ou ao fechar o app).
 *
 * Idempotente: registerUpdateIpc() pode ser chamado N vezes sem duplicar
 * handlers (ipcMain.handle lançaria erro em registro duplicado).
 *
 * Testabilidade: createUpdateState() fábrica da máquina de estados
 * (idle → checking → available → downloading → ready | up-to-date | error).
 * O módulo usa uma instância padrão; os testes criam as suas com
 * autoUpdater falso (EventEmitter) — sem depender de Electron.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.createUpdateState = createUpdateState;
exports.registerUpdateIpc = registerUpdateIpc;
exports.setupAutoUpdate = setupAutoUpdate;
const electron_1 = require("electron");
const electron_updater_1 = require("electron-updater");
const logger_1 = require("./logger");
/**
 * Máquina de estados do auto-update.
 * wire(autoUpdater) conecta os eventos do electron-updater ao estado.
 */
function createUpdateState(deps = {}) {
    const log = deps.log ?? (() => { });
    let state = {
        status: "idle", // idle | checking | available | downloading | ready | error | up-to-date
        version: null,
        progress: 0,
        error: null,
    };
    const listeners = new Set();
    function get() {
        return state;
    }
    function set(patch) {
        state = { ...state, ...patch };
        for (const listener of listeners) {
            try {
                listener(state);
            }
            catch {
                /* listener quebrado não derruba o updater */
            }
        }
        return state;
    }
    function subscribe(fn) {
        listeners.add(fn);
        return () => listeners.delete(fn);
    }
    function wire(autoUpdater) {
        autoUpdater.on("checking-for-update", () => {
            log("info", "updater", "verificando atualizações…");
            set({ status: "checking" });
        });
        autoUpdater.on("update-available", (info) => {
            log("info", "updater", `nova versão disponível: v${info.version}`);
            set({ status: "available", version: info.version, error: null });
        });
        autoUpdater.on("update-not-available", (info) => {
            log("info", "updater", `sem atualizações (v${info.version} é a mais recente)`);
            set({ status: "up-to-date", version: info.version, error: null });
        });
        autoUpdater.on("download-progress", (p) => {
            set({ status: "downloading", progress: Math.round(p.percent || 0) });
        });
        autoUpdater.on("update-downloaded", (info) => {
            log("info", "updater", `v${info.version} baixada — pronta para instalar`);
            set({ status: "ready", version: info.version, progress: 100 });
            // NÃO força quitAndInstall aqui — o usuário decide na UI.
        });
        autoUpdater.on("error", (err) => {
            // Sem rede / sem release publicada ainda — loga e segue sem travar o app.
            log("warn", "updater", `erro: ${String(err?.message ?? err)}`);
            set({ status: "error", error: String(err?.message ?? err) });
        });
    }
    return { get, set, subscribe, wire };
}
// Instância padrão do módulo (usada pelo app real).
const update = createUpdateState({ log: logger_1.logLine });
let ipcRegistered = false;
let checkTimer = null;
function broadcastUpdateState() {
    try {
        for (const win of electron_1.BrowserWindow.getAllWindows()) {
            if (!win.isDestroyed())
                win.webContents.send("update:state", update.get());
        }
    }
    catch (err) {
        logger_1.logLine("warn", "updater", `broadcast falhou: ${String(err)}`);
    }
}
function registerUpdateIpc() {
    if (ipcRegistered)
        return;
    ipcRegistered = true;
    electron_1.ipcMain.handle("update:check", async () => {
        try {
            await electron_updater_1.autoUpdater.checkForUpdates();
            return { ok: true, state: update.get() };
        }
        catch (err) {
            return { ok: false, error: String(err?.message ?? err) };
        }
    });
    electron_1.ipcMain.handle("update:install", async () => {
        try {
            // isSilent=false (instalador visível), isForceRunAfter=true (reabre o app)
            electron_updater_1.autoUpdater.quitAndInstall(false, true);
            return { ok: true };
        }
        catch (err) {
            return { ok: false, error: String(err?.message ?? err) };
        }
    });
    electron_1.ipcMain.handle("update:state", async () => update.get());
}
/**
 * Liga o auto-update. Só atua com app empacotado (dev não tem release).
 * Idempotente: chamado em cada did-finish-load, mas o interval é único.
 *
 * @param getChannel retorna o canal de settings.json ("latest" | "beta" | ...)
 */
function setupAutoUpdate(getChannel) {
    if (!electron_1.app.isPackaged) {
        logger_1.logLine("info", "updater", "app não empacotado — auto-update desligado (dev)");
        return;
    }
    electron_updater_1.autoUpdater.autoDownload = true;
    electron_updater_1.autoUpdater.autoInstallOnAppQuit = true;
    electron_updater_1.autoUpdater.allowDowngrade = false;
    electron_updater_1.autoUpdater.allowPrerelease = false;
    // Canal configurável via settings.json (opcional, default: latest)
    try {
        const channel = getChannel?.();
        if (channel && channel !== "latest") {
            electron_updater_1.autoUpdater.channel = channel;
            electron_updater_1.autoUpdater.allowPrerelease = channel !== "latest";
        }
    }
    catch { /* settings indisponível — segue com default */ }
    // Eventos → máquina de estados; mudança de estado → broadcast ao renderer.
    update.wire(electron_updater_1.autoUpdater);
    update.subscribe(() => broadcastUpdateState());
    // Checagem inicial: 15s após o renderer carregar (não compete com o boot do backend).
    setTimeout(() => {
        electron_updater_1.autoUpdater.checkForUpdatesAndNotify().catch((err) => {
            logger_1.logLine("warn", "updater", `checagem inicial falhou: ${String(err?.message ?? err)}`);
        });
    }, 15_000);
    // Re-checagem a cada 6h (interval único — guard contra chamadas repetidas).
    if (checkTimer === null) {
        checkTimer = setInterval(() => {
            electron_updater_1.autoUpdater.checkForUpdates().catch(() => { /* offline — tenta de novo em 6h */ });
        }, 6 * 60 * 60 * 1000);
    }
}
//# sourceMappingURL=updater.js.map
