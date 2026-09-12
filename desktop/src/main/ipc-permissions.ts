// @ts-nocheck
"use strict";
/**
 * ipc-permissions — camada de permissão para handlers IPC nativos (P0 3.6).
 *
 * NOTA ARQUITETURAL (regra das 3 camadas do roadmap):
 * A UI do GasFlow roda no FastAPI (o Electron carrega http://127.0.0.1:<porta>),
 * então as rotas web já são validadas pelo backend (require_permission).
 * Esta camada cobre APENAS os handlers IPC nativos do main process
 * (printToPDF, shell.openExternal, etc.) — não é a camada primária de
 * segurança; é a terceira barreira do requisito "frontend + IPC + backend".
 *
 * Uso:
 *   registerProtectedHandler("finance:export-pdf", "finance.export_pdf", async (event, args) => {...});
 *
 * O token vem do localStorage da janela (mesma origem do login web) —
 * injetado via registrarTokenProvider() pelo index.ts.
 */

Object.defineProperty(exports, "__esModule", { value: true });
exports.PermissionGate = PermissionGate;
exports.registerProtectedHandler = registerProtectedHandler;
exports.registerTokenProvider = registerTokenProvider;
exports.clearPermissionCache = clearPermissionCache;

const node_http_1 = require("node:http");
const node_url_1 = require("node:url");

// ── Estado do módulo ─────────────────────────────────────────
let tokenProvider = null; // () => Promise<string> | string | null
let permissionCache = null; // { permissions, hasPermission, fetchedAt }
const CACHE_TTL_MS = 30_000; // 30s — evita bater no backend a cada invoke
let backendBaseUrl = "http://127.0.0.1:8000";

function registerTokenProvider(provider) {
    tokenProvider = provider;
}

function setBackendBaseUrl(url) {
    backendBaseUrl = url;
}

function clearPermissionCache() {
    permissionCache = null;
}

// ── HTTP util (node:http — sem dependência nova) ─────────────
function fetchJson(url, headers, timeoutMs = 5000) {
    return new Promise((resolve, reject) => {
        const req = (0, node_http_1.request)(url, { headers, method: "GET" }, (res) => {
            let body = "";
            res.setEncoding("utf8");
            res.on("data", (chunk) => (body += chunk));
            res.on("end", () => {
                try {
                    resolve({ status: res.statusCode || 0, body: JSON.parse(body) });
                } catch {
                    reject(new Error(`resposta inválida do backend (${res.statusCode})`));
                }
            });
        });
        req.setTimeout(timeoutMs, () => {
            req.destroy(new Error("timeout consultando permissões"));
        });
        req.on("error", reject);
        req.end();
    });
}

// ── Gate ─────────────────────────────────────────────────────
function createPermissionGate(options = {}) {
    const ttl = options.cacheTtlMs ?? CACHE_TTL_MS;
    let cache = null;
    const fetcher = options.fetchPermissions ?? fetchPermissionsFromBackend;

    /**
     * Consulta GET /auth/me e extrai permissions (fonte: PermissionPolicyLoader).
     * Falha fechada: sem token/erro → permissões vazias.
     */
    async function fetchPermissionsFromBackend() {
        const token = tokenProvider ? await tokenProvider() : null;
        if (!token) return [];
        try {
            const { status, body } = await fetchJson(
                `${backendBaseUrl}/auth/me`,
                { Authorization: `Bearer ${token}` }
            );
            if (status !== 200 || !Array.isArray(body.permissions)) return [];
            return body.permissions;
            } catch {
            return [];
        }
    }

    async function getPermissions() {
        if (cache && Date.now() - cache.fetchedAt < ttl) return cache.permissions;
        const permissions = await fetcher();
        cache = { permissions, fetchedAt: Date.now() };
        return permissions;
    }

    /** admin.* concede tudo; módulo.* cobre o recurso (mesma semântica do backend). */
    function hasPermission(permissions, permission) {
        if (permissions.includes("admin.*")) return true;
        if (permissions.includes(permission)) return true;
        const resource = permission.split(".")[0];
        return permissions.includes(`${resource}.*`);
    }

    return {
        async check(permission) {
            const permissions = await getPermissions();
            return hasPermission(permissions, permission);
        },
        async checkAndThrow(permission) {
            if (!(await this.check(permission))) {
                const err = new Error(`Permission '${permission}' required`);
                err.code = "IPC_PERMISSION_DENIED";
                throw err;
            }
        },
        _debug: {
            reset: () => (cache = null),
            stats: () => ({ cached: !!cache, fetchedAt: cache?.fetchedAt ?? null }),
        },
    };
}

const defaultGate = createPermissionGate();

/**
 * Registra handler IPC protegido por permissão.
 * Rejeita (throw) antes de executar o handler se a permissão não está presente.
 */
function registerProtectedHandler(channel, permission, handler) {
    const { ipcMain } = require("electron");
    ipcMain.handle(channel, async (event, ...args) => {
        await defaultGate.checkAndThrow(permission);
        return handler(event, ...args);
    });
}

function PermissionGate() {
    return defaultGate;
}

// Export interno para testes (gate isolado com fetcher injetado).
function forTesting() {
    return { createPermissionGate, setBackendBaseUrl };
}
exports.forTesting = forTesting;
