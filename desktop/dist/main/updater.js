"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createUpdateState = createUpdateState;
exports.registerUpdateIpc = registerUpdateIpc;
exports.setupAutoUpdate = setupAutoUpdate;
const electron_2 = require("electron");
const electron_updater_1 = require("electron-updater");
const logger_2 = require("./logger");
function createUpdateState(deps = {}) {
    const log = deps.log ?? (() => undefined);
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
                // Um listener quebrado não deve derrubar o updater.
            }
        }
        return state;
    }
    function subscribe(fn) {
        listeners.add(fn);
        return () => listeners.delete(fn);
    }
    function wire(updater) {
        updater.on("checking-for-update", () => {
            log("info", "updater", "verificando atualizações…");
            set({ status: "checking" });
        });
        updater.on("update-available", (info) => {
            log("info", "updater", `nova versão disponível: v${info.version}`);
            set({ status: "available", version: info.version, error: null });
        });
        updater.on("update-not-available", (info) => {
            log("info", "updater", `sem atualizações (v${info.version} é a mais recente)`);
            set({ status: "up-to-date", version: info.version, error: null });
        });
        updater.on("download-progress", (progress) => {
            set({ status: "downloading", progress: Math.round(progress.percent || 0) });
        });
        updater.on("update-downloaded", (info) => {
            log("info", "updater", `v${info.version} baixada — pronta para instalar`);
            set({ status: "ready", version: info.version, progress: 100 });
        });
        updater.on("error", (error) => {
            const message = error instanceof Error ? error.message : String(error);
            log("warn", "updater", `erro: ${message}`);
            set({ status: "error", error: message });
        });
    }
    return { get, set, subscribe, wire };
}
const update = createUpdateState({ log: (level, scope, message) => (0, logger_2.logLine)(level, scope, message) });
let ipcRegistered = false;
let checkTimer = null;
function errorMessage(error) {
    return error instanceof Error ? error.message : String(error);
}
function broadcastUpdateState() {
    try {
        for (const win of electron_2.BrowserWindow.getAllWindows()) {
            if (!win.isDestroyed())
                win.webContents.send("update:state", update.get());
        }
    }
    catch (error) {
        (0, logger_2.logLine)("warn", "updater", `broadcast falhou: ${errorMessage(error)}`);
    }
}
function registerUpdateIpc() {
    if (ipcRegistered)
        return;
    ipcRegistered = true;
    electron_2.ipcMain.handle("update:check", async () => {
        try {
            await electron_updater_1.autoUpdater.checkForUpdates();
            return { ok: true, state: update.get() };
        }
        catch (error) {
            return { ok: false, error: errorMessage(error) };
        }
    });
    electron_2.ipcMain.handle("update:install", async () => {
        try {
            electron_updater_1.autoUpdater.quitAndInstall(false, true);
            return { ok: true };
        }
        catch (error) {
            return { ok: false, error: errorMessage(error) };
        }
    });
    electron_2.ipcMain.handle("update:state", async () => update.get());
}
/**
 * Liga o auto-update. Só atua com app empacotado (dev não tem release).
 * Idempotente: chamado em cada did-finish-load, mas o interval é único.
 *
 * @param getChannel retorna o canal de settings.json ("latest" | "beta" | ...)
 */
function setupAutoUpdate(getChannel) {
    if (!electron_2.app.isPackaged) {
        (0, logger_2.logLine)("info", "updater", "app não empacotado — auto-update desligado (dev)");
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
        electron_updater_1.autoUpdater.checkForUpdatesAndNotify().catch((error) => {
            (0, logger_2.logLine)("warn", "updater", `checagem inicial falhou: ${errorMessage(error)}`);
        });
    }, 15_000);
    // Re-checagem a cada 6h (interval único — guard contra chamadas repetidas).
    if (checkTimer === null) {
        checkTimer = setInterval(() => {
            electron_updater_1.autoUpdater.checkForUpdates().catch(() => undefined);
        }, 6 * 60 * 60 * 1000);
    }
}
//# sourceMappingURL=updater.js.map
