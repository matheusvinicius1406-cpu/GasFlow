"use strict";
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
exports.TEST_RECEIPT_ESCPOS = void 0;
exports.backendPort = backendPort;
exports.backendUrl = backendUrl;
exports.waBaseUrl = waBaseUrl;
exports.sqliteDatabaseUrl = sqliteDatabaseUrl;
exports.resolveFrontendDist = resolveFrontendDist;
exports.resolvePython = resolvePython;
exports.sanitizePdfFilename = sanitizePdfFilename;
exports.isSessionToken = isSessionToken;
exports.planServices = planServices;
/**
 * Helpers puros do main process (index.ts).
 *
 * Motivo da separação: index.ts aciona o boot do Electron no require, então
 * nada nele é importável num teste. Aqui ficam as decisões de configuração e
 * formatação — todas sem dependência do Electron (fs/path entram injetados),
 * de modo que tests/app-helpers.test.ts cubra o comportamento sem GUI.
 */
const path = __importStar(require("node:path"));
/** Porta do backend a partir de settings.gasflowApiUrl (default 8000). */
function backendPort(apiUrl) {
    const m = (apiUrl || "").match(/:(\d+)/);
    return m ? Number.parseInt(m[1], 10) : 8000;
}
/** Base URL local do backend FastAPI. */
function backendUrl(apiUrl) {
    return `http://127.0.0.1:${backendPort(apiUrl)}`;
}
/** Base URL local do serviço WhatsApp (porta vinda de settings.waPort). */
function waBaseUrl(waPort) {
    return `http://127.0.0.1:${waPort}`;
}
/** URL SQLAlchemy do SQLite embutido no userData (separador sempre "/"). */
function sqliteDatabaseUrl(userData) {
    return `sqlite:///${path.join(userData, "gasflow.db").replace(/\\/g, "/")}`;
}
/** Frontend servido pelo backend: recursos do pacote em prod, dist local em dev. */
function resolveFrontendDist(opts) {
    if (opts.isPackaged) {
        return path.join(opts.resourcesPath, "frontend");
    }
    return opts.exists(opts.devDist) ? opts.devDist : "";
}
/** Python do backend: binário empacotado → venv local → python do PATH. */
function resolvePython(opts) {
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
function sanitizePdfFilename(filename, fallback = "nota-compra.pdf") {
    const name = typeof filename === "string" && filename ? filename : fallback;
    return name.replace(/[^a-zA-Z0-9._-]/g, "_");
}
/** Token de sessão reportado pelo renderer é válido só quando é string. */
function isSessionToken(token) {
    return typeof token === "string";
}
/** Cupom de teste em ESC/POS (80mm): inicializa, escreve e corta. */
exports.TEST_RECEIPT_ESCPOS = "\x1b@" + "\x1b\x21\x10" + "        GASFLOW         \n" + "\x1b\x21\x00" +
    "------------------------------------------\n" +
    "     TESTE DE IMPRESSORA\n" +
    "------------------------------------------\n" +
    "Se este cupom saiu, a impressora esta\n" +
    "configurada e os cupons de pedido vao\n" +
    "sair automaticamente.\n" +
    "------------------------------------------\n" +
    "\n\n\n" + "\x1bi";
/**
 * Quais serviços o boot deve subir. Flags default OFF só quando explícitas
 * (`!== false`), preservando instalações antigas sem a chave no settings.json.
 */
function planServices(settings) {
    const whatsapp = settings.waEnabled !== false;
    return {
        whatsapp,
        assistant: whatsapp && Boolean(settings.waAutoReply),
        printer: settings.printerEnabled !== false,
        waWebPanel: settings.waWebPanel?.enabled === true,
        relay: Boolean(settings.relayEnabled && settings.relayUrl),
    };
}
//# sourceMappingURL=app-helpers.js.map