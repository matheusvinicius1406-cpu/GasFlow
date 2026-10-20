/**
 * Helpers puros do main process (index.ts).
 *
 * Motivo da separação: index.ts aciona o boot do Electron no require, então
 * nada nele é importável num teste. Aqui ficam as decisões de configuração e
 * formatação — todas sem dependência do Electron (fs/path entram injetados),
 * de modo que tests/app-helpers.test.ts cubra o comportamento sem GUI.
 */
import * as path from "node:path";

/** Porta do backend a partir de settings.gasflowApiUrl (default 8000). */
export function backendPort(apiUrl: string): number {
    const m = (apiUrl || "").match(/:(\d+)/);
    return m ? Number.parseInt(m[1], 10) : 8000;
}

/** Base URL local do backend FastAPI. */
export function backendUrl(apiUrl: string): string {
    return `http://127.0.0.1:${backendPort(apiUrl)}`;
}

/** Base URL local do serviço WhatsApp (porta vinda de settings.waPort). */
export function waBaseUrl(waPort: number | string): string {
    return `http://127.0.0.1:${waPort}`;
}

/** URL SQLAlchemy do SQLite embutido no userData (separador sempre "/"). */
export function sqliteDatabaseUrl(userData: string): string {
    return `sqlite:///${path.join(userData, "gasflow.db").replace(/\\/g, "/")}`;
}

export interface FrontendDistOptions {
    isPackaged: boolean;
    resourcesPath: string;
    devDist: string;
    exists: (p: string) => boolean;
}

/** Frontend servido pelo backend: recursos do pacote em prod, dist local em dev. */
export function resolveFrontendDist(opts: FrontendDistOptions): string {
    if (opts.isPackaged) {
        return path.join(opts.resourcesPath, "frontend");
    }
    return opts.exists(opts.devDist) ? opts.devDist : "";
}

export interface PythonLaunch {
    command: string;
    args: string[];
    cwd: string;
}

export interface PythonOptions {
    isPackaged: boolean;
    resourcesPath: string;
    backendDir: string;
    exists: (p: string) => boolean;
    cwd: string;
}

/** Python do backend: binário empacotado → venv local → python do PATH. */
export function resolvePython(opts: PythonOptions): PythonLaunch {
    if (opts.isPackaged) {
        const packagedBackend = path.join(opts.backendDir, "gasflow-backend.exe");
        if (opts.exists(packagedBackend)) {
            return { command: packagedBackend, args: [], cwd: opts.backendDir };
        }
    }
    const venvPython = path.join(opts.backendDir, ".venv", "Scripts", "python.exe");
    const cwd = opts.exists(path.join(opts.backendDir, "app", "main.py")) ? opts.backendDir : opts.cwd;
    const args = ["-m", "uvicorn", "app.main:app"];
    if (opts.exists(venvPython)) {
        return { command: venvPython, args, cwd };
    }
    return { command: "python", args, cwd };
}

/**
 * Nome de arquivo do PDF de compra: só [a-zA-Z0-9._-], restante vira "_" (evita
 * path traversal no caminho do tmp). Valor vazio/não-string cai no fallback.
 */
export function sanitizePdfFilename(filename: unknown, fallback = "nota-compra.pdf"): string {
    const name = typeof filename === "string" && filename ? filename : fallback;
    return name.replace(/[^a-zA-Z0-9._-]/g, "_");
}

/** Token de sessão reportado pelo renderer é válido só quando é string. */
export function isSessionToken(token: unknown): token is string {
    return typeof token === "string";
}

/** Cupom de teste em ESC/POS (80mm): inicializa, escreve e corta. */
export const TEST_RECEIPT_ESCPOS = "\x1b@" + "\x1b\x21\x10" + "        GASFLOW         \n" + "\x1b\x21\x00" +
    "------------------------------------------\n" +
    "     TESTE DE IMPRESSORA\n" +
    "------------------------------------------\n" +
    "Se este cupom saiu, a impressora esta\n" +
    "configurada e os cupons de pedido vao\n" +
    "sair automaticamente.\n" +
    "------------------------------------------\n" +
    "\n\n\n" + "\x1bi";

export interface ServicePlanSettings {
    waEnabled?: boolean;
    waAutoReply?: boolean;
    printerEnabled?: boolean;
    waWebPanel?: { enabled?: boolean } | undefined;
    relayEnabled?: boolean;
    relayUrl?: string;
}

export interface ServicePlan {
    whatsapp: boolean;
    assistant: boolean;
    printer: boolean;
    waWebPanel: boolean;
    relay: boolean;
}

/**
 * Quais serviços o boot deve subir. Flags default OFF só quando explícitas
 * (`!== false`), preservando instalações antigas sem a chave no settings.json.
 */
export function planServices(settings: ServicePlanSettings): ServicePlan {
    const whatsapp = settings.waEnabled !== false;
    return {
        whatsapp,
        assistant: whatsapp && Boolean(settings.waAutoReply),
        printer: settings.printerEnabled !== false,
        waWebPanel: settings.waWebPanel?.enabled === true,
        relay: Boolean(settings.relayEnabled && settings.relayUrl),
    };
}
