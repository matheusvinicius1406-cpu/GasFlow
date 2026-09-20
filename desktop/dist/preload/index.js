// @ts-nocheck
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Preload — ponte segura entre renderer (React) e main process.
 * contextIsolation: o renderer não tem acesso a Node; só a esta API.
 */
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
function subscribe(channel, callback) {
    const listener = (_event, ...args) => callback(...args);
    electron_1.ipcRenderer.on(channel, listener);
    return () => electron_1.ipcRenderer.removeListener(channel, listener);
}
const api = {
    // Settings
    getSettings: () => electron_1.ipcRenderer.invoke("settings:get"),
    saveSettings: (patch) => electron_1.ipcRenderer.invoke("settings:set", patch),
    // Agente de integração
    agentStart: () => electron_1.ipcRenderer.invoke("agent:start"),
    agentStop: () => electron_1.ipcRenderer.invoke("agent:stop"),
    agentStatus: () => electron_1.ipcRenderer.invoke("agent:status"),
    listIntegrations: () => electron_1.ipcRenderer.invoke("agent:list-integrations"),
    syncAgent: (integrationId) => electron_1.ipcRenderer.invoke("agent:sync", { integrationId }),
    // IA (Ollama)
    aiStatus: () => electron_1.ipcRenderer.invoke("ai:status"),
    // IA no boot (Item 3): status do setup, download e eventos
    aiSetupStatus: () => electron_1.ipcRenderer.invoke("ai:setup-status"),
    aiSetupRetry: () => electron_1.ipcRenderer.invoke("ai:setup-retry"),
    aiDownloadModel: (model) => electron_1.ipcRenderer.invoke("ai:setup-download", model),
    onAiStatusChanged: (cb) => subscribe("ai:status-changed", cb),
    onAiDownloadProgress: (cb) => subscribe("ai:download-progress", cb),
    // App do Entregador (Fase 1): localização em tempo real via relay
    onDriverLocation: (cb) => subscribe("gasflow:driver-location", cb),
    whisperStatus: () => electron_1.ipcRenderer.invoke("ai:whisper-status"),
    extractFromHtml: (html, model) => electron_1.ipcRenderer.invoke("ai:extract-html", { html, model }),
    extractFromImage: (base64, model) => electron_1.ipcRenderer.invoke("ai:extract-image", { base64, model }),
    extractFromText: (text, model) => electron_1.ipcRenderer.invoke("ai:extract-text", { text, model }),
    transcribeAudio: (filePath) => electron_1.ipcRenderer.invoke("ai:transcribe", { filePath }),
    // Envio de pedidos + saúde
    sendOrders: (integrationId, orders) => electron_1.ipcRenderer.invoke("orders:send", { integrationId, orders }),
    gasflowHealth: () => electron_1.ipcRenderer.invoke("gasflow:health"),
    // Notas de compra (Item 2): PDF via printToPDF em janela offscreen
    exportPdf: (html, filename) => electron_1.ipcRenderer.invoke("purchase:export-pdf", { html, filename }),
    // F9: relatórios — printToPDF da view atual (gráficos já renderizados)
    exportCurrentViewPdf: () => electron_1.ipcRenderer.invoke("reports:export-pdf"),
    // Diálogos
    pickImage: () => electron_1.ipcRenderer.invoke("dialog:pick-image"),
    pickAudio: () => electron_1.ipcRenderer.invoke("dialog:pick-audio"),
    pickHtml: () => electron_1.ipcRenderer.invoke("dialog:pick-html"),
    // WhatsApp local (serviço embutido)
    waStart: () => electron_1.ipcRenderer.invoke("wa:start"),
    waStop: () => electron_1.ipcRenderer.invoke("wa:stop"),
    waStatus: () => electron_1.ipcRenderer.invoke("wa:status"),
    waListAccounts: () => electron_1.ipcRenderer.invoke("wa:list-accounts"),
    waStartAccount: (accountId) => electron_1.ipcRenderer.invoke("wa:start-account", { accountId }),
    waStopAccount: (accountId) => electron_1.ipcRenderer.invoke("wa:stop-account", { accountId }),
    waLogoutAccount: (accountId) => electron_1.ipcRenderer.invoke("wa:logout-account", { accountId }),
    waGetQr: (accountId) => electron_1.ipcRenderer.invoke("wa:get-qr", { accountId }),
    waSend: (accountId, recipient, text) => electron_1.ipcRenderer.invoke("wa:send", { accountId, recipient, text }),
    waSetAutoReply: (enabled) => electron_1.ipcRenderer.invoke("wa:auto-reply", { enabled }),
    // WhatsApp Web panel (protótipo, flag waWebPanel.enabled)
    waWebStatuses: () => electron_1.ipcRenderer.invoke("wa-web:statuses"),
    waWebShow: (accountId, bounds) => electron_1.ipcRenderer.invoke("wa-web:show", { accountId, bounds }),
    waWebBounds: (bounds) => electron_1.ipcRenderer.invoke("wa-web:bounds", { bounds }),
    waWebHide: (accountId) => electron_1.ipcRenderer.invoke("wa-web:hide", { accountId }),
    waWebRePair: (accountId) => electron_1.ipcRenderer.invoke("wa-web:re-pair", { accountId }),
    waWebClose: (accountId) => electron_1.ipcRenderer.invoke("wa-web:close", { accountId }),
    onWaWebStatus: (cb) => subscribe("gasflow:wa-web-status", cb),
    // Impressão (F10.7): impressoras instaladas, escolha, estado e teste.
    // Só existem dentro do Electron — no navegador `gasflow` não é exposto.
    printerList: () => electron_1.ipcRenderer.invoke("printer:list"),
    printerSetName: (name) => electron_1.ipcRenderer.invoke("settings:setPrinterName", name),
    printerStatus: () => electron_1.ipcRenderer.invoke("printer:status"),
    printerTest: () => electron_1.ipcRenderer.invoke("printer:test"),
    // Conversas WhatsApp (gateway do backend)
    listConversations: () => electron_1.ipcRenderer.invoke("convs:list"),
    getConversation: (id) => electron_1.ipcRenderer.invoke("convs:get", { id }),
    takeoverConversation: (id, operator) => electron_1.ipcRenderer.invoke("convs:takeover", { id, operator }),
    releaseConversation: (id) => electron_1.ipcRenderer.invoke("convs:release", { id }),
    replyConversation: (id, text) => electron_1.ipcRenderer.invoke("convs:reply", { id, text }),
    suggestReply: (id) => electron_1.ipcRenderer.invoke("convs:suggest", { id }),
    // Sessão (P0 3.6): o renderer reporta o token pós-login e sinaliza
    // mudanças (logout/change-password) para o gate de permissões IPC.
    reportSessionToken: (token) => electron_1.ipcRenderer.invoke("auth:session-token", token),
    notifySessionChanged: () => electron_1.ipcRenderer.invoke("auth:session-changed"),
    // Eventos push
    onLog: (cb) => subscribe("gasflow:log", cb),
    onAgentOutcome: (cb) => subscribe("gasflow:agent-outcome", cb),
    onAgentStatus: (cb) => subscribe("gasflow:agent-status", cb),
    onWaStatus: (cb) => subscribe("gasflow:wa-status", cb),
};
electron_1.contextBridge.exposeInMainWorld("gasflow", api);
/**
 * Auto-update — exposto separadamente (window.gasflowUpdater).
 * No navegador (dev fora do Electron) `gasflowUpdater` não existe.
 */
const updaterApi = {
    check: () => electron_1.ipcRenderer.invoke("update:check"),
    install: () => electron_1.ipcRenderer.invoke("update:install"),
    getState: () => electron_1.ipcRenderer.invoke("update:state"),
    onStateChange: (cb) => subscribe("update:state", cb),
};
electron_1.contextBridge.exposeInMainWorld("gasflowUpdater", updaterApi);
//# sourceMappingURL=index.js.map