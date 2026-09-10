// @ts-nocheck
"use strict";
/**
 * Configurações persistidas do app desktop.
 *
 * Grava em <userData>/settings.json (Electron resolve o caminho por SO).
 * Defaults alinhados com o backend (OLLAMA_MODEL=llama3.2, whisper "base").
 * O token do GasFlow é sensível: fica apenas no disco local do usuário,
 * nunca em log.
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
exports.loadSettings = loadSettings;
exports.saveSettings = saveSettings;
const electron_1 = require("electron");
const fs = __importStar(require("node:fs"));
const path = __importStar(require("node:path"));
const DEFAULTS = {
    gasflowApiUrl: "http://localhost:8000",
    gasflowToken: "",
    ollamaBaseUrl: "http://localhost:11434",
    ollamaTextModel: "llama3.2",
    ollamaVisionModel: "llama3.2-vision",
    // Backend local (uvicorn) — senha do login admin/original do frontend
    backendAdminPassword: "",
    // WhatsApp local (serviço embutido no app desktop)
    // waEnabled controla se o waBridge sobe no boot (default true — comportamento
    // histórico; false pula o start do serviço WhatsApp).
    waEnabled: true,
    waPort: 3101,
    waApiKey: "",
    waAutoReply: false,
};
function generateKey(prefix) {
    return `${prefix}-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}
function settingsPath() {
    return path.join(electron_1.app.getPath("userData"), "settings.json");
}
function loadSettings() {
    let loaded;
    try {
        const raw = fs.readFileSync(settingsPath(), "utf-8");
        const parsed = JSON.parse(raw);
        loaded = { ...DEFAULTS, ...parsed };
    }
    catch {
        loaded = { ...DEFAULTS };
    }
    // Chaves sensíveis geradas na primeira execução e persistidas.
    let changed = false;
    if (!loaded.waApiKey) {
        loaded.waApiKey = generateKey("wa");
        changed = true;
    }
    if (!loaded.backendAdminPassword) {
        loaded.backendAdminPassword = generateKey("admin");
        changed = true;
    }
    if (changed)
        saveSettings(loaded);
    // Arquivo de login sempre atualizado — sem ele o usuário não descobre a
    // senha gerada para entrar no frontend (login admin).
    try {
        fs.writeFileSync(path.join(path.dirname(settingsPath()), "LOGIN.txt"), `GasFlow Desktop — login do painel\n\n` +
            `Usuário: admin\n` +
            `Senha:   ${loaded.backendAdminPassword}\n\n` +
            `(troque "backendAdminPassword" em settings.json e reinicie o app para usar outra senha)\n`, "utf-8");
    }
    catch {
        /* best-effort */
    }
    return loaded;
}
function saveSettings(settings) {
    const dir = path.dirname(settingsPath());
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(settingsPath(), JSON.stringify(settings, null, 2), "utf-8");
}
//# sourceMappingURL=config.js.map
