import { app } from "electron";
import fs from "node:fs";
import path from "node:path";

export interface Settings {
  gasflowApiUrl: string;
  gasflowToken: string;
  ollamaBaseUrl: string;
  ollamaTextModel: string;
  ollamaVisionModel: string;
  backendAdminPassword: string;
  waEnabled: boolean;
  waPort: number;
  waApiKey: string;
  waAutoReply: boolean;
  updateChannel?: string;
}

const DEFAULTS: Settings = {
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

function generateKey(prefix: string): string {
    return `${prefix}-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

function settingsPath(): string {
  return path.join(app.getPath("userData"), "settings.json");
}

export function loadSettings(): Settings {
  let loaded: Settings;
    try {
    const raw = fs.readFileSync(settingsPath(), "utf-8");
    const parsed: unknown = JSON.parse(raw);
    const saved = parsed && typeof parsed === "object" ? parsed : {};
    loaded = { ...DEFAULTS, ...saved } as Settings;
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

export function saveSettings(settings: Settings): void {
    const dir = path.dirname(settingsPath());
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(settingsPath(), JSON.stringify(settings, null, 2), "utf-8");
}
