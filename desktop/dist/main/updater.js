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
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.registerUpdateIpc = registerUpdateIpc;
exports.setupAutoUpdate = setupAutoUpdate;
const electron_1 = require("electron");
const electron_updater_1 = require("electron-updater");
const logger_1 = require("./logger");
let updateState = {
    status: "idle", // idle | checking | available | downloading | ready | error | up-to-date
    version: null,
    progress: 0,
    error: null,
};
let ipcRegistered = false;
let checkTimer = null;
function broadcastUpdateState() {
    try {
        for (const win of electron_1.BrowserWindow.getAllWindows()) {
            if (!win.isDestroyed())
                win.webContents.send("update:state", updateState);
        }
    }
    catch (err) {
        logger_1.logLine("warn", "updater", `broadcast falhou: ${String(err)}`);
    }
}
function setState(patch) {
    updateState = { ...updateState, ...patch };
    broadcastUpdateState();
}
function registerUpdateIpc() {
    if (ipcRegistered)
        return;
    ipcRegistered = true;
    electron_1.ipcMain.handle("update:check", async () => {
        try {
            await electron_updater_1.autoUpdater.checkForUpdates();
            return { ok: true, state: updateState };
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
    electron_1.ipcMain.handle("update:state", async () => updateState);
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
    electron_updater_1.autoUpdater.on("checking-for-update", () => {
        logger_1.logLine("info", "updater", "verificando atualizações…");
        setState({ status: "checking" });
    });
    electron_updater_1.autoUpdater.on("update-available", (info) => {
        logger_1.logLine("info", "updater", `nova versão disponível: v${info.version}`);
        setState({ status: "available", version: info.version, error: null });
    });
    electron_updater_1.autoUpdater.on("update-not-available", (info) => {
        logger_1.logLine("info", "updater", `sem atualizações (v${info.version} é a mais recente)`);
        setState({ status: "up-to-date", version: info.version, error: null });
    });
    electron_updater_1.autoUpdater.on("download-progress", (p) => {
        setState({ status: "downloading", progress: Math.round(p.percent || 0) });
    });
    electron_updater_1.autoUpdater.on("update-downloaded", (info) => {
        logger_1.logLine("info", "updater", `v${info.version} baixada — pronta para instalar`);
        setState({ status: "ready", version: info.version, progress: 100 });
        // NÃO força quitAndInstall aqui — o usuário decide na UI.
    });
    electron_updater_1.autoUpdater.on("error", (err) => {
        // Sem rede / sem release publicada ainda — loga e segue sem travar o app.
        logger_1.logLine("warn", "updater", `erro: ${String(err?.message ?? err)}`);
        setState({ status: "error", error: String(err?.message ?? err) });
    });
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
