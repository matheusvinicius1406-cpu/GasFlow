"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.loadSettings = loadSettings;
exports.saveSettings = saveSettings;
const electron_2 = require("electron");
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
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
    return node_path_1.default.join(electron_2.app.getPath("userData"), "settings.json");
}
function loadSettings() {
    let loaded;
    try {
        const raw = node_fs_1.default.readFileSync(settingsPath(), "utf-8");
        const parsed = JSON.parse(raw);
        const saved = parsed && typeof parsed === "object" ? parsed : {};
        loaded = { ...DEFAULTS, ...saved };
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
        node_fs_1.default.writeFileSync(node_path_1.default.join(node_path_1.default.dirname(settingsPath()), "LOGIN.txt"), `GasFlow Desktop — login do painel\n\n` +
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
    const dir = node_path_1.default.dirname(settingsPath());
    node_fs_1.default.mkdirSync(dir, { recursive: true });
    node_fs_1.default.writeFileSync(settingsPath(), JSON.stringify(settings, null, 2), "utf-8");
}
//# sourceMappingURL=config.js.map
