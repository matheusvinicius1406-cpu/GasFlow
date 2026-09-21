// @ts-nocheck
"use strict";
/**
 * Preload — ponte segura entre renderer (React) e main process.
 * contextIsolation: o renderer não tem acesso a Node; só a esta API.
 *
 * A UI viva é o React servido pelo FastAPI (o main faz
 * `mainWindow.loadURL(backendUrl())`). O renderer antigo
 * (`desktop/dist/renderer`, nunca carregado) foi removido, e com ele os
 * canais IPC que só ele usava — a ponte abaixo é exatamente o que o
 * renderer vivo consome (verificado pelo guard `tests/test_app_integrity.py`).
 */
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
function subscribe(channel, callback) {
    const listener = (_event, ...args) => callback(...args);
    electron_1.ipcRenderer.on(channel, listener);
    return () => electron_1.ipcRenderer.removeListener(channel, listener);
}
const api = {
    // Notas de compra: PDF via printToPDF em janela offscreen
    exportPdf: (html, filename) => electron_1.ipcRenderer.invoke("purchase:export-pdf", { html, filename }),
    // F9: relatórios — printToPDF da view atual (gráficos já renderizados)
    exportCurrentViewPdf: () => electron_1.ipcRenderer.invoke("reports:export-pdf"),
    // Impressão (F10.7): impressoras instaladas, escolha, estado e teste.
    // Só existem dentro do Electron — no navegador `gasflow` não é exposto.
    printerList: () => electron_1.ipcRenderer.invoke("printer:list"),
    printerSetName: (name) => electron_1.ipcRenderer.invoke("settings:setPrinterName", name),
    printerStatus: () => electron_1.ipcRenderer.invoke("printer:status"),
    printerTest: () => electron_1.ipcRenderer.invoke("printer:test"),
    // WhatsApp Web panel (protótipo, flag waWebPanel.enabled)
    waWebStatuses: () => electron_1.ipcRenderer.invoke("wa-web:statuses"),
    waWebShow: (accountId, bounds) => electron_1.ipcRenderer.invoke("wa-web:show", { accountId, bounds }),
    waWebBounds: (bounds) => electron_1.ipcRenderer.invoke("wa-web:bounds", { bounds }),
    waWebHide: (accountId) => electron_1.ipcRenderer.invoke("wa-web:hide", { accountId }),
    waWebRePair: (accountId) => electron_1.ipcRenderer.invoke("wa-web:re-pair", { accountId }),
    waWebClose: (accountId) => electron_1.ipcRenderer.invoke("wa-web:close", { accountId }),
    onWaWebStatus: (cb) => subscribe("gasflow:wa-web-status", cb),
    // Sessão (P0 3.6): o renderer reporta o token pós-login e sinaliza
    // mudanças (logout/change-password) para o gate de permissões IPC.
    reportSessionToken: (token) => electron_1.ipcRenderer.invoke("auth:session-token", token),
    notifySessionChanged: () => electron_1.ipcRenderer.invoke("auth:session-changed"),
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
