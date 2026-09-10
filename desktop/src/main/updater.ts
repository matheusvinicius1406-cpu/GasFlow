import { app, BrowserWindow, ipcMain } from "electron";
import { autoUpdater, type UpdateInfo, type ProgressInfo } from "electron-updater";
import { logLine } from "./logger";

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
/**
 * Máquina de estados do auto-update.
 * wire(autoUpdater) conecta os eventos do electron-updater ao estado.
 */
export type UpdateStatus = "idle" | "checking" | "available" | "downloading" | "ready" | "error" | "up-to-date";
export interface UpdateState {
    status: UpdateStatus;
    version: string | null;
    progress: number;
    error: string | null;
}

type UpdateLog = (level: "info" | "warn", scope: string, message: string) => void;
type UpdateStateListener = (state: UpdateState) => void;
type AutoUpdaterLike = {
    on: (event: string, listener: (...args: any[]) => void) => unknown;
};

export function createUpdateState(deps: { log?: (level: "info" | "warn", scope: string, message: string) => void } = {}) {
    const log: UpdateLog = deps.log ?? (() => undefined);
    let state: UpdateState = {
        status: "idle", // idle | checking | available | downloading | ready | error | up-to-date
        version: null,
        progress: 0,
        error: null,
    };
    const listeners = new Set<UpdateStateListener>();
    function get(): UpdateState {
        return state;
    }
    function set(patch: Partial<UpdateState>): UpdateState {
        state = { ...state, ...patch };
        for (const listener of listeners) {
            try {
                listener(state);
            } catch {
                // Um listener quebrado não deve derrubar o updater.
            }
    }
        return state;
    }
    function subscribe(fn: UpdateStateListener): () => boolean {
        listeners.add(fn);
        return () => listeners.delete(fn);
    }
    function wire(updater: AutoUpdaterLike): void {
        updater.on("checking-for-update", () => {
            log("info", "updater", "verificando atualizações…");
            set({ status: "checking" });
        });
        updater.on("update-available", (info: UpdateInfo) => {
            log("info", "updater", `nova versão disponível: v${info.version}`);
            set({ status: "available", version: info.version, error: null });
        });
        updater.on("update-not-available", (info: UpdateInfo) => {
            log("info", "updater", `sem atualizações (v${info.version} é a mais recente)`);
            set({ status: "up-to-date", version: info.version, error: null });
        });
        updater.on("download-progress", (progress: ProgressInfo) => {
            set({ status: "downloading", progress: Math.round(progress.percent || 0) });
        });
        updater.on("update-downloaded", (info: UpdateInfo) => {
            log("info", "updater", `v${info.version} baixada — pronta para instalar`);
            set({ status: "ready", version: info.version, progress: 100 });
        });
        updater.on("error", (error: unknown) => {
            const message = error instanceof Error ? error.message : String(error);
            log("warn", "updater", `erro: ${message}`);
            set({ status: "error", error: message });
        });
    }
    return { get, set, subscribe, wire };
}

const update = createUpdateState({ log: (level, scope, message) => logLine(level, scope, message) });
let ipcRegistered = false;
let checkTimer: ReturnType<typeof setInterval> | null = null;

function errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
}

function broadcastUpdateState(): void {
    try {
        for (const win of BrowserWindow.getAllWindows()) {
            if (!win.isDestroyed()) win.webContents.send("update:state", update.get());
    }
    } catch (error) {
        logLine("warn", "updater", `broadcast falhou: ${errorMessage(error)}`);
    }
}

export function registerUpdateIpc(): void {
    if (ipcRegistered) return;
    ipcRegistered = true;
    ipcMain.handle("update:check", async () => {
        try {
            await autoUpdater.checkForUpdates();
            return { ok: true, state: update.get() };
        } catch (error) {
            return { ok: false, error: errorMessage(error) };
    }
    });
    ipcMain.handle("update:install", async () => {
        try {
            autoUpdater.quitAndInstall(false, true);
            return { ok: true };
        } catch (error) {
            return { ok: false, error: errorMessage(error) };
        }
    });
    ipcMain.handle("update:state", async () => update.get());
}
/**
 * Liga o auto-update. Só atua com app empacotado (dev não tem release).
 * Idempotente: chamado em cada did-finish-load, mas o interval é único.
 *
 * @param getChannel retorna o canal de settings.json ("latest" | "beta" | ...)
 */
export function setupAutoUpdate(getChannel?: () => string | undefined): void {
    if (!app.isPackaged) {
        logLine("info", "updater", "app não empacotado — auto-update desligado (dev)");
        return;
    }
    autoUpdater.autoDownload = true;
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.allowDowngrade = false;
    autoUpdater.allowPrerelease = false;
    // Canal configurável via settings.json (opcional, default: latest)
    try {
        const channel = getChannel?.();
        if (channel && channel !== "latest") {
            autoUpdater.channel = channel;
            autoUpdater.allowPrerelease = channel !== "latest";
        }
    } catch { /* settings indisponível — segue com default */ }
    // Eventos → máquina de estados; mudança de estado → broadcast ao renderer.
    update.wire(autoUpdater);
    update.subscribe(() => broadcastUpdateState());
    // Checagem inicial: 15s após o renderer carregar (não compete com o boot do backend).
    setTimeout(() => {
        autoUpdater.checkForUpdatesAndNotify().catch((error: unknown) => {
            logLine("warn", "updater", `checagem inicial falhou: ${errorMessage(error)}`);
        });
    }, 15_000);
    // Re-checagem a cada 6h (interval único — guard contra chamadas repetidas).
    if (checkTimer === null) {
        checkTimer = setInterval(() => {
            autoUpdater.checkForUpdates().catch(() => undefined);
        }, 6 * 60 * 60 * 1000);
    }
}
