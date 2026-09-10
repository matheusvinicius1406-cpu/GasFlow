// @ts-nocheck
"use strict";
/**
 * WhatsAppBridge — roda o serviço whatsapp/ como subprocesso e fala REST
 * com ele (mesmos endpoints usados pelo backend: /api/whatsapp/*).
 *
 * Caminhos de sessão/banco são redirecionados para o userData do app
 * (DATA_DIR, BAILEYS_AUTH_DIR) para não sujar o diretório de instalação.
 *
 * Sem dependência do Electron (testável); paths resolvidos em main/index.ts.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.WhatsAppBridge = void 0;
const node_child_process_1 = require("node:child_process");
const node_events_1 = require("node:events");
class WhatsAppBridge extends node_events_1.EventEmitter {
    opts;
    child = null;
    constructor(opts) {
        super();
        this.opts = opts;
    }
    get running() {
        return this.child !== null && this.child.exitCode === null;
    }
    status() {
        return { running: this.running, pid: this.child?.pid, url: this.opts.baseUrl };
    }
    /** Inicia o serviço (idempotente) e aguarda /api/health responder. */
    async start(waitMs = 20_000) {
        if (this.running)
            return this.status();
        const child = (0, node_child_process_1.spawn)(this.opts.command, this.opts.args, {
            cwd: this.opts.cwd,
            env: { ...process.env, ...this.opts.env },
            stdio: ["ignore", "pipe", "pipe"],
            windowsHide: true,
        });
        this.child = child;
        this.emit("status", this.status());
        const forward = (buf, level) => {
            for (const line of buf.split(/\r?\n/)) {
                if (line.trim())
                    this.emit("log", { level, scope: "whatsapp", message: line.trim() });
            }
        };
        child.stdout?.setEncoding("utf-8");
        child.stdout?.on("data", (d) => forward(d, "info"));
        child.stderr?.setEncoding("utf-8");
        child.stderr?.on("data", (d) => forward(d, "error"));
        child.on("error", (e) => this.emit("log", { level: "error", scope: "whatsapp", message: `falha ao iniciar: ${e.message}` }));
        child.on("exit", (code) => {
            this.child = null;
            this.emit("log", {
                level: "info",
                scope: "whatsapp",
                message: `serviço whatsapp encerrado (code=${code ?? "?"})`,
            });
            this.emit("status", this.status());
        });
        // Aguarda o Express subir (poll /api/health).
        const deadline = Date.now() + waitMs;
        while (Date.now() < deadline) {
            if (!this.running)
                throw new Error("serviço whatsapp saiu durante a inicialização");
            try {
                const res = await this.request("GET", "/api/health", undefined, 2000);
                if (res.ok)
                    return this.status();
            }
            catch {
                /* ainda subindo */
            }
            await new Promise((r) => setTimeout(r, 400));
        }
        throw new Error(`serviço whatsapp não respondeu em ${Math.round(waitMs / 1000)}s`);
    }
    async stop() {
        const child = this.child;
        if (!child)
            return;
        this.child = null;
        child.kill();
        await new Promise((resolve) => {
            const timer = setTimeout(() => {
                child.kill("SIGKILL");
                resolve();
            }, 3000);
            child.once("exit", () => {
                clearTimeout(timer);
                resolve();
            });
        });
        this.emit("status", this.status());
    }
    async request(method, path, body, timeoutMs) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs ?? this.opts.requestTimeoutMs ?? 15_000);
        try {
            const res = await (this.opts.fetchFn ?? fetch)(`${this.opts.baseUrl}${path}`, {
                method,
                headers: {
                    "Content-Type": "application/json",
                    ...(this.opts.apiKey ? { Authorization: `Bearer ${this.opts.apiKey}` } : {}),
                },
                body: body === undefined ? undefined : JSON.stringify(body),
                signal: controller.signal,
            });
            const data = (await res.json().catch(() => ({})));
            return { ok: res.ok, status: res.status, data };
        }
        finally {
            clearTimeout(timer);
        }
    }
    assertOk(res) {
        if (!res.ok) {
            const d = res.data;
            throw new Error(d.detail ?? d.error ?? `HTTP ${res.status}`);
        }
    }
    async listAccounts() {
        const res = await this.request("GET", "/api/whatsapp/accounts");
        this.assertOk(res);
        return (res.data.accounts ?? []);
    }
    async startAccount(accountId) {
        this.assertOk(await this.request("POST", `/api/whatsapp/accounts/${accountId}/start`, {}));
    }
    async stopAccount(accountId) {
        this.assertOk(await this.request("POST", `/api/whatsapp/accounts/${accountId}/stop`, {}));
    }
    async logoutAccount(accountId) {
        this.assertOk(await this.request("POST", `/api/whatsapp/accounts/${accountId}/logout`, {}));
    }
    /** QR code como data URL pronto para <img src>. 404 → null (sem QR pendente). */
    async getQr(accountId) {
        const res = await this.request("GET", `/api/whatsapp/accounts/${accountId}/qr`);
        if (!res.ok)
            return null;
        const d = res.data;
        return d.dataUrl ? { dataUrl: d.dataUrl, qr: d.qr ?? "", expiresIn: d.expiresIn ?? 0 } : null;
    }
    async sendMessage(accountId, recipient, text) {
        const res = await this.request("POST", `/api/whatsapp/accounts/${accountId}/messages`, {
            recipient,
            message: text,
        });
        if (!res.ok) {
            const d = res.data;
            return { success: false, error: d.detail ?? d.error ?? `HTTP ${res.status}` };
        }
        const d = res.data;
        return { success: true, messageId: d.messageId, duplicate: d.duplicate };
    }
}
exports.WhatsAppBridge = WhatsAppBridge;
//# sourceMappingURL=wa-bridge.js.map
