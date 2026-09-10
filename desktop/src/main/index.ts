// @ts-nocheck
"use strict";
/**
 * GasFlow Desktop — main process (container do frontend original).
 *
 * Arquitetura: o Electron NÃO tem interface própria. Ele:
 *   1. sobe o backend FastAPI (uvicorn), que serve o frontend React
 *      original + as APIs (/api);
 *   2. sobe o serviço WhatsApp (Baileys) e o agente de integração;
 *   3. abre uma janela carregando http://127.0.0.1:<porta> — a mesma
 *      experiência do navegador, com tudo rodando local.
 *
 * O assistente IA (auto-resposta de WhatsApp via Ollama) continua no main
 * process, controlado por settings.waAutoReply (settings.json).
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const fs = __importStar(require("node:fs"));
const path = __importStar(require("node:path"));
const path_1 = __importStar(require("node:path"));
const agent_bridge_1 = require("./agent-bridge");
const assistant_1 = require("./assistant");
const backend_bridge_1 = require("./backend-bridge");
const config_1 = require("./config");
const gasflow_1 = require("./gasflow");
const logger_1 = require("./logger");
const ai_service_1 = require("./ai-service");
const wa_bridge_1 = require("./wa-bridge");
const updater_1 = require("./updater");
let mainWindow = null;
let settings = (0, config_1.loadSettings)();
let ai;
let backend;
let bridge;
let waBridge;
let assistant = null;
// ── Helpers ──────────────────────────────────────────────────────────
function backendPort() {
    const m = settings.gasflowApiUrl.match(/:(\d+)/);
    return m ? Number.parseInt(m[1], 10) : 8000;
}
function backendUrl() {
    return `http://127.0.0.1:${backendPort()}`;
}
function waBaseUrl() {
    return `http://127.0.0.1:${settings.waPort}`;
}
function notify(title, body) {
    try {
        if (mainWindow?.isFocused())
            return;
        if (!electron_1.Notification.isSupported())
            return;
        new electron_1.Notification({ title, body, silent: false }).show();
    }
    catch {
        /* best-effort */
    }
}
function resolveFrontendDist() {
    if (electron_1.app.isPackaged) {
        return path.join(process.resourcesPath, "frontend");
    }
    const devDist = path.join(__dirname, "..", "..", "..", "frontend", "dist");
    return fs.existsSync(devDist) ? devDist : "";
}
/** Python do backend: prefere venv local, senão python do PATH. */
function resolvePython() {
    const backendDir = electron_1.app.isPackaged
        ? path.join(process.resourcesPath, "backend")
        : path.join(__dirname, "..", "..", "..", "backend");
    if (electron_1.app.isPackaged) {
        const packagedBackend = path.join(backendDir, "gasflow-backend.exe");
        if (fs.existsSync(packagedBackend)) {
            return { command: packagedBackend, args: [], cwd: backendDir };
        }
    }
    const venvPython = path.join(backendDir, ".venv", "Scripts", "python.exe");
    const cwd = fs.existsSync(path.join(backendDir, "app", "main.py")) ? backendDir : process.cwd();
    if (fs.existsSync(venvPython)) {
        return { command: venvPython, args: ["-m", "uvicorn", "app.main:app"], cwd };
    }
    return { command: "python", args: ["-m", "uvicorn", "app.main:app"], cwd };
}
// ── Serviços ─────────────────────────────────────────────────────────
function ensureBackend() {
    if (backend)
        return backend;
    const { command, args, cwd } = resolvePython();
    const userData = electron_1.app.getPath("userData");
    const sqliteUrl = `sqlite:///${path.join(userData, "gasflow.db").replace(/\\/g, "/")}`;
    backend = new backend_bridge_1.BackendBridge({
        command,
        args: [...args, "--host", "127.0.0.1", "--port", String(backendPort())],
        cwd,
        healthUrl: `${backendUrl()}/health`,
        env: {
            DATABASE_URL: sqliteUrl,
            ADMIN_PASSWORD: settings.backendAdminPassword,
            FRONTEND_DIST: resolveFrontendDist(),
            WHATSAPP_SERVICE_URL: waBaseUrl(),
            WHATSAPP_SERVICE_KEY: settings.waApiKey,
            MARCOS_GAS_API_KEY: settings.waApiKey,
            AI_PROVIDER: "ollama",
            OLLAMA_BASE_URL: settings.ollamaBaseUrl,
            OLLAMA_MODEL: settings.ollamaTextModel,
            ENVIRONMENT: "production",
        },
    }, (level, scope, message) => logger_1.logger[level](scope, message));
    return backend;
}
function ensureWaBridge() {
    if (waBridge)
        return waBridge;
    const waDist = path.join(__dirname, "..", "..", "..", "whatsapp", "dist", "server.js");
    const useDist = electron_1.app.isPackaged || fs.existsSync(waDist);
    const command = useDist ? process.execPath : "npx";
    const args = useDist
        ? [electron_1.app.isPackaged ? path.join(process.resourcesPath, "whatsapp", "dist", "server.js") : waDist]
        : ["tsx", "src/server.ts"];
    const userData = electron_1.app.getPath("userData");
    waBridge = new wa_bridge_1.WhatsAppBridge({
        command,
        args,
        cwd: useDist ? undefined : path.join(__dirname, "..", "..", "..", "whatsapp"),
        env: {
            PORT: String(settings.waPort),
            DATA_DIR: path.join(userData, "whatsapp-data"),
            BAILEYS_AUTH_DIR: path.join(userData, "baileys_auth"),
            MARCOS_GAS_API_KEY: settings.waApiKey,
            GASFLOW_SERVICE_KEY: settings.waApiKey,
            GASFLOW_BACKEND_URL: backendUrl(),
            ...(useDist ? { ELECTRON_RUN_AS_NODE: "1" } : { WA_DEV: "1" }),
        },
        baseUrl: waBaseUrl(),
        apiKey: settings.waApiKey,
    });
    waBridge.on("log", ({ level, scope, message }) => logger_1.logger[level === "warn" ? "warn" : level](scope, message));
    waBridge.on("status", (s) => notify(s.running ? "💬 WhatsApp iniciado" : "💬 WhatsApp parado", `Serviço em ${settings.waPort}`));
    return waBridge;
}
function ensureAgentBridge() {
    if (bridge)
        return bridge;
    const agentDist = path.join(__dirname, "..", "..", "..", "agent", "dist", "index.js");
    const useDist = electron_1.app.isPackaged || fs.existsSync(agentDist);
    bridge = new agent_bridge_1.AgentBridge({
        command: useDist ? process.execPath : "npx",
        args: useDist
            ? [electron_1.app.isPackaged ? path.join(process.resourcesPath, "agent", "dist", "index.js") : agentDist, "--ipc"]
            : ["tsx", "src/index.ts", "--ipc"],
        cwd: useDist ? undefined : path.join(__dirname, "..", "..", "..", "agent"),
        env: useDist ? { ELECTRON_RUN_AS_NODE: "1" } : { AGENT_DEV: "1" },
        getCredentials: () => ({ apiUrl: backendUrl(), token: settings.gasflowToken }),
    });
    bridge.on("log", ({ level, scope, message }) => logger_1.logger[level === "warn" ? "warn" : level](scope, message));
    bridge.on("outcome", (outcome) => {
        logger_1.logger.info("agent", `[${outcome.integrationName}] ${outcome.message}`);
        notify(outcome.ok ? "✅ Sincronização concluída" : "❌ Falha na sincronização", `[${outcome.integrationName}] ${outcome.message}`);
    });
    bridge.on("status", (s) => {
        notify(s.running ? "🔄 Agente iniciado" : "🔄 Agente parado", "");
    });
    return bridge;
}

async function startWithRetry(label: string, start: () => Promise<unknown>, attempts = 3): Promise<void> {
    let lastError: unknown;
    for (let attempt = 1; attempt <= attempts; attempt++) {
        try {
            await start();
            logger.info(`${label}.started`, `tentativa=${attempt}`);
            return;
        } catch (error) {
            lastError = error;
            logger.warn(`${label}.start_failed`, `tentativa=${attempt}/${attempts}: ${error instanceof Error ? error.message : String(error)}`);
            if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, 1500));
        }
    }
    throw lastError instanceof Error ? lastError : new Error(`${label} não iniciou`);
}
// ── IPC de settings ─────────────────────────────────────────────
// settings:setWaEnabled — liga/desliga o serviço WhatsApp em runtime.
// Persiste em settings.json e inicia/para o waBridge conforme o novo valor.
function registerSettingsIpc() {
    electron_1.ipcMain.handle("settings:setWaEnabled", async (_event, enabled) => {
        const next = enabled === true;
        settings = { ...settings, waEnabled: next };
        (0, config_1.saveSettings)(settings);
        if (next) {
            logger_1.logger.info("wa.bridge", "waEnabled=true — iniciando waBridge");
            try {
                await ensureWaBridge().start();
                if (settings.waAutoReply)
                    ensureAssistant().start();
                return { ok: true, running: true };
            }
            catch (e) {
                logger_1.logger.warn("wa.bridge", `falha ao iniciar: ${e.message}`);
                return { ok: false, running: false, error: String(e.message) };
            }
        }
        logger_1.logger.info("wa.bridge", "waEnabled=false — parando waBridge");
        if (waBridge && typeof waBridge.stop === "function") {
            try {
                await waBridge.stop();
                return { ok: true, running: false };
            }
            catch (e) {
                logger_1.logger.warn("wa.bridge", `falha ao parar: ${e.message}`);
                return { ok: false, running: true, error: String(e.message) };
            }
        }
        // Bridge nem chegou a ser instanciado (boot com waEnabled=false) — nada a parar.
        logger_1.logger.info("wa.bridge", "waBridge não instanciado — nada a parar");
        return { ok: true, running: false };
    });
}
function ensureAssistant() {
    if (assistant)
        return assistant;
    const client = new gasflow_1.GasFlowClient({ baseUrl: backendUrl(), token: settings.gasflowToken });
    assistant = new assistant_1.AssistantEngine({
        client,
        bridge: ensureWaBridge(),
        chat: (prompt, opts) => ai.chat(prompt, { system: opts?.system, temperature: 0.4, numPredict: 512 }),
        autoReply: () => settings.waAutoReply,
    });
    return assistant;
}
// ── Janela ───────────────────────────────────────────────────────────
function createWindow() {
    mainWindow = new electron_1.BrowserWindow({
        width: 1360,
        height: 860,
        minWidth: 1024,
        title: "GasFlow",
        backgroundColor: "#0f1117",
        show: false,
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            // Ponte IPC (window.gasflow + window.gasflowUpdater) — dist/preload/index.js.
            preload: path_1.default.join(__dirname, "..", "preload", "index.js"),
        },
    });
    // Logger espelha linhas para o renderer (console de logs da UI).
    logger_1.setRendererSender((channel, payload) => {
        try {
            if (mainWindow && !mainWindow.isDestroyed())
                mainWindow.webContents.send(channel, payload);
        }
        catch { /* janela fechando */ }
    });
    mainWindow.webContents.on("did-finish-load", () => {
        // Renderer pronto: registra handlers e inicia o auto-update.
        (0, updater_1.registerUpdateIpc)();
        (0, updater_1.setupAutoUpdate)(() => settings.updateChannel);
    });
    mainWindow.once("ready-to-show", () => mainWindow?.show());
    void mainWindow.loadURL(backendUrl());
    mainWindow.on("closed", () => (mainWindow = null));
}
// ── Lifecycle ────────────────────────────────────────────────────────
const gotLock = electron_1.app.requestSingleInstanceLock();
if (!gotLock) {
    electron_1.app.quit();
}
else {
    electron_1.app.on("second-instance", () => mainWindow?.focus());
    electron_1.app.whenReady().then(async () => {
        // Handlers de settings registrados cedo — o renderer pode chamar a
        // qualquer momento depois do preload.
        registerSettingsIpc();
        ai = new ai_service_1.AiService({
            baseUrl: settings.ollamaBaseUrl,
            textModel: settings.ollamaTextModel,
            visionModel: settings.ollamaVisionModel,
        });
        try {
            await startWithRetry("backend", () => ensureBackend().start());
            createWindow();
            logger_1.logger.info("app", `backend pronto em ${backendUrl()} — frontend original servido pelo FastAPI`);
        }
        catch (e) {
            logger_1.logger.error("app", `backend não subiu: ${e.message}`);
            // Janela de erro mínima (sem interface custom) — mensagem nativa.
            const { dialog } = await Promise.resolve().then(() => __importStar(require("electron")));
            await dialog.showErrorBox("GasFlow Desktop", `O backend não conseguiu iniciar.\n\n${e.message}\n\n` +
                "Feche outras instâncias do GasFlow e tente novamente. Se o problema continuar,\n" +
                "consulte os logs em %APPDATA%\\gasflow-desktop\\logs.");
            electron_1.app.quit();
            return;
        }
        // Serviços em segundo plano — independentes: falha de um não trava o outro.
        // waEnabled=false pula o boot do serviço WhatsApp (settings.json).
        if (settings.waEnabled !== false) {
            void startWithRetry("wa.bridge", () => ensureWaBridge().start())
                .then(() => {
                if (settings.waAutoReply)
                    ensureAssistant().start();
            })
                .catch((e) => logger_1.logger.warn("app", `whatsapp: ${e.message}`));
        }
        else {
            logger_1.logger.info("wa.bridge.skipped", "waEnabled=false");
        }
        void startWithRetry("agent", () => ensureAgentBridge().start())
            .catch((e) => logger_1.logger.warn("app", `agente: ${e.message}`));
        electron_1.app.on("activate", () => {
            if (electron_1.BrowserWindow.getAllWindows().length === 0)
                createWindow();
        });
    });
    electron_1.app.on("window-all-closed", () => {
        void bridge?.stop();
        void waBridge?.stop();
        void backend?.stop();
        if (process.platform !== "darwin")
            electron_1.app.quit();
    });
}
//# sourceMappingURL=index.js.map
