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
const ai_setup_1 = require("./ai-setup");
const relay_client_1 = require("./relay-client");
const wa_bridge_1 = require("./wa-bridge");
// Protótipo WhatsApp Web (pairing/status apenas — envio segue no Baileys).
const wa_web_panel_1 = require("./wa-web-panel");
const updater_1 = require("./updater");
// P0 3.6 — gate de permissão para handlers IPC nativos (defesa em profundidade).
const ipc_permissions_1 = require("./ipc-permissions");
let mainWindow = null;
let settings = (0, config_1.loadSettings)();
let ai;
let backend;
let bridge;
let waBridge;
let assistant = null;
let aiSetup = null;
let relayClient = null;
const relay_ingest_1 = require("./relay-ingest");
let waWebPanel = null;
// F10.3 — orquestrador: mantém os serviços vivos enquanto o app estiver aberto.
const { ServiceOrchestrator } = require("./orchestrator");
const { PrintWorker } = require("./print-worker");
const { printRawBytes } = require("./print-transport");
let orchestrator = null;
let printWorker = null;
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
        ? [electron_1.app.isPackaged ? path.join("whatsapp", "dist", "server.js") : waDist]
        : ["tsx", "src/server.ts"];
    const userData = electron_1.app.getPath("userData");
    waBridge = new wa_bridge_1.WhatsAppBridge({
        command,
        args,
        cwd: useDist ? (electron_1.app.isPackaged ? process.resourcesPath : undefined) : path.join(__dirname, "..", "..", "..", "whatsapp"),
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
            ? [electron_1.app.isPackaged ? path.join("agent", "dist", "index.js") : agentDist, "--ipc"]
            : ["tsx", "src/index.ts", "--ipc"],
        cwd: useDist ? (electron_1.app.isPackaged ? process.resourcesPath : undefined) : path.join(__dirname, "..", "..", "..", "agent"),
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

// ── F10.3 — Orquestrador de serviços ─────────────────────────────────
// Desired-state: cada serviço tem health check periódico e restart com
// backoff. Enquanto o app estiver aberto, um serviço que cai volta sozinho;
// após muitas falhas consecutivas o restart pausa (com notificação) em vez
// de ficar em crash-loop eterno. Estado de saúde persiste em userData.
function ensureOrchestrator() {
    if (orchestrator) return orchestrator;
    orchestrator = new ServiceOrchestrator();
    const userData = electron_1.app.getPath("userData");
    orchestrator.setPersistence(path.join(userData, "health-state.json"));

    const onEvent = (event) => {
        logger_1.logger.info("orchestrator", `${event.service}: ${event.type} — ${event.detail} (tentativa=${event.attempts})`);
        if (event.type === "paused") {
            notify("GasFlow — serviço pausado", `${event.service}: várias falhas seguidas. Abra Configurações para retomar.`);
        }
    };

    // Backend (API central + frontend servido). Health: GET /health.
    orchestrator.register({
        name: "backend",
        start: () => ensureBackend().start(),
        stop: () => ensureBackend().stop(),
        isHealthy: async () => {
            try {
                const res = await fetch(`${backendUrl()}/health`, { signal: AbortSignal.timeout(2000) });
                return res.ok;
            } catch {
                return false;
            }
        },
        onEvent,
    });

    // Serviço WhatsApp (Baileys). Health: GET /api/health.
    orchestrator.register({
        name: "whatsapp",
        start: () => ensureWaBridge().start(),
        stop: () => ensureWaBridge().stop(),
        isHealthy: async () => {
            try {
                const res = await fetch(`${waBaseUrl()}/api/health`, { signal: AbortSignal.timeout(2000) });
                return res.ok;
            } catch {
                return false;
            }
        },
        onEvent,
    });

    // Agente de integração (subprocesso Node, JSON-lines sobre stdio).
    // Health = processo vivo: o agente roda mesmo sem token configurado (só
    // loga aviso), então sair é o único sinal confiável de queda — e é
    // exatamente o caso que precisa de restart automático.
    orchestrator.register({
        name: "agent",
        start: () => ensureAgentBridge().start(),
        stop: () => ensureAgentBridge().stop(),
        isHealthy: async () => ensureAgentBridge().status().running,
        onEvent,
    });

    // Impressão (F10.7): worker que consome a fila do backend e manda os
    // bytes ESC/POS para a impressora USB desta máquina. Health = ticks
    // recentes; "doente" = parou de consultar a fila.
    orchestrator.register({
        name: "printer",
        start: async () => {
            ensurePrintWorker().start();
        },
        stop: async () => {
            printWorker?.stop();
        },
        isHealthy: async () => ensurePrintWorker().isHealthy(),
        onEvent,
    });

    return orchestrator;
}

function ensurePrintWorker() {
    if (!printWorker) {
        printWorker = new PrintWorker({
            baseUrl: backendUrl(),
            // Mesma chave de serviço que o backend recebe no boot (X-GasFlow-Key).
            serviceKey: settings.waApiKey,
            printerName: settings.printerName || "",
            // Anti-duplicata: o backend devolve o job à fila quando o POST do
            // resultado se perde, e o cupom não pode sair duas vezes.
            ledgerPath: path.join(electron_1.app.getPath("userData"), "printed-jobs.json"),
            onEvent: (event) => {
                logger_1.logger.info("print", `${event.type}: ${event.detail}`);
                if (event.type === "failed") {
                    notify("GasFlow — falha na impressão", event.detail);
                }
                else if (event.type === "expired") {
                    // Cupom de dia anterior que não saiu: sem aviso, o pedido fica
                    // sem cupom e ninguém percebe (não sai papel, então não há erro).
                    notify("GasFlow — cupons não impressos", event.detail);
                }
            },
        });
    }
    else {
        // Configurações podem ter mudado sem reiniciar o app.
        printWorker.setPrinterName(settings.printerName || "");
    }
    return printWorker;
}
/** Boot de um serviço sob orquestração — nunca rejeita (log + notificação). */
function startOrchestrated(name) {
    const orch = ensureOrchestrator();
    return orch.start(name).catch((e) => {
        logger_1.logger.warn("orchestrator", `${name}: boot inicial falhou — o health loop vai tentar de novo (${e.message})`);
    });
}
// ── IPC protegido (P0 3.6) ─────────────────────────────────────
// O token de sessão vive no localStorage da janela (mesma origem do login
// web) — o renderer o reporta ao main a cada login/logout/change-password,
// e o gate consulta /auth/me no backend local com cache de 30s.
// handlers IPC protegidos (defesa em profundidade — a validação primária
// permanece no backend via require_permission).
function registerProtectedIpc() {
    electron_1.ipcMain.handle("auth:session-token", (_event, token) => {
        if (typeof token !== "string")
            return { ok: false };
        (0, ipc_permissions_1.registerTokenProvider)(() => token);
        ipc_permissions_1.clearPermissionCache();
        logger_1.logger.info("ipc.permissions", "token de sessão atualizado");
        return { ok: true };
    });
    electron_1.ipcMain.handle("auth:session-changed", () => {
        // login/logout/change-password: força refetch de permissões.
        ipc_permissions_1.clearPermissionCache();
        return { ok: true };
    });
    // reports:export-pdf (F9) → printToPDF da view atual: os gráficos da
    // ReportsPage já estão renderizados no DOM, então imprimimos a própria
    // janela (paisagem — gráficos lado a lado) e salvamos no tmp.
    // Permissão: finance.export_pdf.
    (0, ipc_permissions_1.registerProtectedHandler)("reports:export-pdf", "finance.export_pdf", async (event) => {
        const wc = event.sender;
        const pdf = await wc.printToPDF({
            landscape: true,
            printBackground: true,
            margins: { top: 0.4, bottom: 0.4, left: 0.4, right: 0.4 },
        });
        const { shell } = require("electron");
        const { writeFile } = require("node:fs/promises");
        const { tmpdir } = require("node:os");
        const { join } = require("node:path");
        const outPath = join(tmpdir(), `gasflow-relatorio-entregas-${Date.now()}.pdf`);
        await writeFile(outPath, pdf);
        await shell.openPath(outPath);
        return { ok: true, path: outPath };
    });
    // purchase:export-pdf → printToPDF do webContents (handler nativo).
    // Recebe HTML já autorizado (o backend só devolve html para purchase.read);
    // aqui o gate garante purchase.read também na barreira IPC.
    (0, ipc_permissions_1.registerProtectedHandler)("purchase:export-pdf", "purchase.read", async (_event, args) => {
        const html = args?.html;
        const filename = typeof args?.filename === "string" ? args.filename : "nota-compra.pdf";
        if (typeof html !== "string" || !html)
            throw new Error("html ausente");
        const { BrowserWindow } = require("electron");
        // Janela offscreen dedicada: o printToPDF usa o conteúdo da nota,
        // não a view atual do app.
        const win = new BrowserWindow({ show: false, webPreferences: { offscreen: true } });
        try {
            await win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
            const pdf = await win.webContents.printToPDF({
                landscape: false,
                printBackground: true,
                margins: { top: 0.4, bottom: 0.4, left: 0.4, right: 0.4 },
            });
            const { shell } = require("electron");
            const { writeFile } = require("node:fs/promises");
            const { tmpdir } = require("node:os");
            const { join } = require("node:path");
            const safeName = filename.replace(/[^a-zA-Z0-9._-]/g, "_");
            const outPath = join(tmpdir(), safeName);
            await writeFile(outPath, pdf);
            await shell.openPath(outPath);
            return { ok: true, path: outPath };
        } finally {
            win.destroy();
        }
    });
}
// ── IPC de settings ─────────────────────────────────────────────
// settings:setWaEnabled — liga/desliga o serviço WhatsApp em runtime.
// Persiste em settings.json e inicia/para o waBridge conforme o novo valor.
// ── WhatsApp Web panel (protótipo, flag waWebPanel.enabled) ─────
// Handlers só existem com a flag ON; com a flag OFF o painel é null e as
// chamadas do renderer respondem { ok:false, disabled:true }.
function ensureWaWebPanel() {
    if (!waWebPanel && settings.waWebPanel?.enabled === true) {
        waWebPanel = wa_web_panel_1.createPanelIfEnabled(settings, {
            attachView: (view) => {
                if (mainWindow && !mainWindow.isDestroyed())
                    mainWindow.contentView.addChildView(view);
            },
            detachView: (view) => {
                try {
                    mainWindow?.contentView.removeChildView(view);
                }
                catch { /* janela fechada */ }
            },
        });
        if (waWebPanel) {
            waWebPanel.onStatus = (status) => {
                if (mainWindow && !mainWindow.isDestroyed())
                    mainWindow.webContents.send("gasflow:wa-web-status", status);
                else
                    bridge?.broadcast?.("gasflow:wa-web-status", status);
            };
        }
    }
    return waWebPanel;
}

function registerWaWebPanelIpc() {
    const guard = async () => {
        const panel = ensureWaWebPanel();
        if (!panel)
            throw new Error("Painel WhatsApp Web está desativado (waWebPanel.enabled=false).");
        return panel;
    };
    electron_1.ipcMain.handle("wa-web:statuses", () => {
        const panel = waWebPanel;
        return { ok: true, enabled: Boolean(panel), statuses: panel ? panel.getStatuses() : wa_web_panel_1.WA_WEB_ACCOUNTS.map((id) => ({ accountId: id, state: "closed", lastEventAt: null, lastError: null })) };
    });
    electron_1.ipcMain.handle("wa-web:show", async (_event, args) => {
        const panel = await guard();
        const accountId = typeof args?.accountId === "string" ? args.accountId : "primary";
        const bounds = args?.bounds && typeof args.bounds === "object" ? args.bounds : undefined;
        await panel.show(accountId, bounds);
        return { ok: true };
    });
    electron_1.ipcMain.handle("wa-web:bounds", async (_event, args) => {
        const panel = waWebPanel;
        if (!panel)
            return { ok: false, disabled: true };
        if (args?.bounds && typeof args.bounds === "object")
            panel.setBounds(args.bounds);
        return { ok: true };
    });
    electron_1.ipcMain.handle("wa-web:hide", async (_event, args) => {
        const panel = waWebPanel;
        if (!panel)
            return { ok: false, disabled: true };
        panel.hide(typeof args?.accountId === "string" ? args.accountId : "primary");
        return { ok: true };
    });
    electron_1.ipcMain.handle("wa-web:re-pair", async (_event, args) => {
        const panel = await guard();
        const accountId = typeof args?.accountId === "string" ? args.accountId : "primary";
        await panel.rePair(accountId);
        return { ok: true };
    });
    electron_1.ipcMain.handle("wa-web:close", async (_event, args) => {
        const panel = waWebPanel;
        if (!panel)
            return { ok: false, disabled: true };
        panel.close(typeof args?.accountId === "string" ? args.accountId : "primary");
        return { ok: true };
    });
}
// ── IPC de settings ─────────────────────────────────────────────
// settings:setWaEnabled — liga/desliga o serviço WhatsApp em runtime.
// Persiste em settings.json e inicia/para o waBridge conforme o novo valor.
function registerSettingsIpc() {
    // ── Impressão (F10.7) ────────────────────────────────
    // Listar as impressoras INSTALADAS no Windows (só o Electron consegue).
    electron_1.ipcMain.handle("printer:list", async () => {
        try {
            const printers = await mainWindow.webContents.getPrintersAsync();
            return {
                ok: true,
                printers: printers.map((p) => ({
                    name: p.name,
                    displayName: p.displayName || p.name,
                    isDefault: p.isDefault === true,
                    status: p.status,
                })),
            };
        }
        catch (e) {
            return { ok: false, printers: [], error: String(e?.message ?? e) };
        }
    });
    // Escolher a impressora: persiste e troca em runtime (sem reiniciar).
    electron_1.ipcMain.handle("settings:setPrinterName", async (_event, name) => {
        const next = typeof name === "string" ? name.trim() : "";
        settings = { ...settings, printerName: next };
        (0, config_1.saveSettings)(settings);
        ensurePrintWorker().setPrinterName(next);
        logger_1.logger.info("print", `impressora definida: ${next || "(nenhuma)"}`);
        return { ok: true, printerName: next };
    });
    // Estado local do worker (impressora, contadores, último erro).
    electron_1.ipcMain.handle("printer:status", () => ({ ok: true, status: ensurePrintWorker().status() }));
    // Teste de impressão: manda o cupom de teste ESC/POS direto para a
    // impressora escolhida e devolve o erro real quando falha.
    electron_1.ipcMain.handle("printer:test", async () => {
        const printerName = settings.printerName || "";
        if (!printerName) {
            return { ok: false, error: "Escolha uma impressora antes de testar." };
        }
        // O cupom de teste é montado aqui (o desktop não importa o formatador
        // Python do backend): só precisa provar que sai papel.
        const testPayload = Buffer.from(TEST_RECEIPT_ESCPOS, "binary");
        const result = await printRawBytes(printerName, testPayload);
        return { ok: result.ok, error: result.error, printerName };
    });
}
// Cupom de teste em ESC/POS (80mm): inicializa, escreve e corta.
const TEST_RECEIPT_ESCPOS = "\x1b@" + "\x1b\x21\x10" + "        GASFLOW         \n" + "\x1b\x21\x00" +
    "------------------------------------------\n" +
    "     TESTE DE IMPRESSORA\n" +
    "------------------------------------------\n" +
    "Se este cupom saiu, a impressora esta\n" +
    "configurada e os cupons de pedido vao\n" +
    "sair automaticamente.\n" +
    "------------------------------------------\n" +
    "\n\n\n" + "\x1bi";
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
// ── IA no boot (Item 3) ─────────────────────────────────────────────
// Fire-and-forget: detecção/instalação/download do modelo rodam em
// background — NUNCA bloqueiam a janela. Cenário B da Fase 4.2: não existe
// serviço externo; sem Ollama local a IA degrada com mensagem controlada.
function ensureAiSetup() {
    if (aiSetup)
        return aiSetup;
    aiSetup = new ai_setup_1.AiSetupRunner({
        baseUrl: settings.ollamaBaseUrl,
        modelName: settings.ollamaTextModel,
        notifyOwner: async (opts) => {
            const { dialog } = await Promise.resolve().then(() => __importStar(require("electron")));
            const { response } = await dialog.showMessageBox(mainWindow, opts);
            return response === 0; // botão "Baixar agora"
        },
        onProgress: (p) => {
            if (mainWindow && !mainWindow.isDestroyed())
                mainWindow.webContents.send("ai:download-progress", p);
        },
        onStatusChanged: (s) => {
            if (mainWindow && !mainWindow.isDestroyed())
                mainWindow.webContents.send("ai:status-changed", s);
        },
        saveState: (s) => {
            settings = (0, ai_setup_1.mergeAiState)(settings, s);
            (0, config_1.saveSettings)(settings);
        },
    });
    return aiSetup;
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
    mainWindow.on("closed", () => {
        // Janela fechando: as views do painel WA Web precisam sair do
        // contentView (attachView as adicionou); sem isso o close quebra.
        try {
            if (waWebPanel) {
                for (const status of waWebPanel.getStatuses()) {
                    waWebPanel.hide(status.accountId);
                }
            }
        }
        catch { /* best-effort */ }
        mainWindow = null;
    });
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
        // Gate de permissões IPC (P0 3.6).
        registerProtectedIpc();
        // Protótipo WhatsApp Web (flag waWebPanel.enabled, default OFF):
        // handlers registrados sempre (respondem disabled com flag off);
        // o painel só nasce quando a flag liga.
        registerWaWebPanelIpc();
        ai = new ai_service_1.AiService({
            baseUrl: settings.ollamaBaseUrl,
            textModel: settings.ollamaTextModel,
            visionModel: settings.ollamaVisionModel,
        });
        try {
            // F10.3: backend sob orquestração — falha no boot não mata o app;
            // o health loop continua tentando (a janela mostra o estado).
            await startOrchestrated("backend");
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
        // Serviços em segundo plano sob orquestração — independentes: falha
        // de um não trava o outro. waEnabled=false pula o WhatsApp.
        if (settings.waEnabled !== false) {
            void startOrchestrated("whatsapp").then(() => {
                if (settings.waAutoReply)
                    ensureAssistant().start();
            });
        }
        else {
            logger_1.logger.info("wa.bridge.skipped", "waEnabled=false");
        }
        // F10.3: agente também sob orquestração (antes só havia retry no boot).
        void startOrchestrated("agent");
        // F10.7: worker de impressão (pula se desligado nas configurações).
        if (settings.printerEnabled !== false) {
            void startOrchestrated("printer");
        }
        else {
            logger_1.logger.info("print", "printerEnabled=false — worker de impressão não iniciado");
        }
        // Protótipo WA Web: painel nasce só com flag on (default OFF) —
        // attach/detach das views fica na janela (createWindow/closed).
        if (settings.waWebPanel?.enabled === true) {
            ensureWaWebPanel();
        }
        else {
            logger_1.logger.info("wa-web-panel", "flag desligada — painel não instanciado");
        }
        // Item 3: IA em background — detecção/consentimento/download nunca
        // bloqueiam o boot (a janela já está aberta aqui).
        void ensureAiSetup()
            .run()
            .catch((e) => logger_1.logger.warn("ai.setup", `boot: ${e.message}`));
        // App do Entregador (Fase 1): relay outbound p/ localização em tempo
        // real. Desligado por padrão (relayEnabled=false no settings.json).
        if (settings.relayEnabled && settings.relayUrl) {
            // Fix do elo morto (rastreador): posição vinda da rua era entregue
            // ao renderer e descartada — o mapa do operador nunca via o
            // entregador fora da WiFi do depósito. Agora o main process ingere
            // no backend embutido (auth service-to-service via X-GasFlow-Key,
            // a mesma settings.waApiKey injetada no backend no boot).
            const relayIngest = new relay_ingest_1.IngestClient({
                baseUrl: backendUrl(),
                serviceKey: settings.waApiKey,
                tenantId: settings.relayTenant || "default",
                log: (level, scope, message) => logger_1.logger[level](scope, message),
            });
            relayClient = new relay_client_1.RelayClient({
                relayUrl: settings.relayUrl,
                tenantId: settings.relayTenant || "default",
                token: settings.relayToken || "",
                log: (scope, message) => logger_1.logger.info(scope, message),
                onLocation: (payload) => {
                    // UI em tempo real (mapa vivo sem esperar o polling de 30s)
                    if (mainWindow && !mainWindow.isDestroyed())
                        mainWindow.webContents.send("gasflow:driver-location", payload);
                    // Persistência: backend → driver_locations → mapa
                    relayIngest.ingestDriverLocation(payload);
                },
                onStatus: (s) => logger_1.logger.info("relay", `status: ${s}`),
            });
            relayClient.start();
        }
        electron_1.app.on("activate", () => {
            if (electron_1.BrowserWindow.getAllWindows().length === 0)
                createWindow();
        });
    });
    electron_1.app.on("before-quit", () => {
        try {
            waWebPanel?.closeAll();
        }
        catch { /* best-effort */ }
        // F10.3: para os health loops e persiste o estado final.
        void orchestrator?.stopAll();
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
