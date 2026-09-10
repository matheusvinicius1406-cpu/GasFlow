"use strict";
/**
 * AgentBridge — roda o agente de integração como subprocesso (`node agent/dist/index.js --ipc`)
 * e fala o protocolo JSON-lines (agent/src/ipc.ts) sobre stdin/stdout.
 *
 * - `request(cmd, params)` correlaciona respostas por id (Promise).
 * - Eventos do agente (ready/log/outcome) são repassados aos handlers.
 * - Após `ready`, envia `configure` automaticamente com as credenciais atuais.
 * - Sem dependência do Electron (testável); paths são resolvidos em main/index.ts.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.AgentBridge = void 0;
const node_child_process_1 = require("node:child_process");
const node_events_1 = require("node:events");
class AgentBridge extends node_events_1.EventEmitter {
    opts;
    child = null;
    pending = new Map();
    nextId = 1;
    stdoutBuffer = "";
    startedAt = 0;
    stopping = false;
    constructor(opts) {
        super();
        this.opts = opts;
    }
    get running() {
        return this.child !== null && this.child.exitCode === null;
    }
    status() {
        return {
            running: this.running,
            pid: this.child?.pid,
            lastError: this.lastError,
        };
    }
    lastError;
    /** Inicia o subprocesso (idempotente). Resolve após o `ready` do agente. */
    async start() {
        if (this.running)
            return this.status();
        this.stopping = false;
        this.lastError = undefined;
        const child = (0, node_child_process_1.spawn)(this.opts.command, this.opts.args, {
            cwd: this.opts.cwd,
            env: { ...process.env, ...this.opts.env },
            stdio: ["pipe", "pipe", "pipe"],
            windowsHide: true,
        });
        this.child = child;
        this.startedAt = Date.now();
        this.emit("status", this.status());
        this.attach(child);
        // ready chega em poucos ms; aguarda para configurar com credenciais.
        await new Promise((resolve) => {
            const onReady = () => {
                this.off("agent-ready", onReady);
                resolve();
            };
            this.on("agent-ready", onReady);
            setTimeout(() => {
                this.off("agent-ready", onReady);
                resolve();
            }, 5000);
        });
        const creds = this.opts.getCredentials();
        if (creds.token) {
            await this.request("configure", { apiUrl: creds.apiUrl, token: creds.token }).catch((e) => {
                this.emit("log", { level: "error", scope: "agent", message: `configure falhou: ${e.message}` });
            });
        }
        else {
            this.emit("log", {
                level: "warn",
                scope: "agent",
                message: "token do GasFlow não configurado — preencha em Configurações e reinicie o agente.",
            });
        }
        return this.status();
    }
    /**
     * Fia stdout/stderr/exit de um child no protocolo. Público para permitir
     * testes com child falso (sem spawn real); start() chama automaticamente.
     */
    attach(child) {
        child.stdout.setEncoding("utf-8");
        child.stdout.on("data", (chunk) => this.onStdout(chunk));
        child.stderr.setEncoding("utf-8");
        child.stderr.on("data", (chunk) => {
            for (const line of chunk.split(/\r?\n/)) {
                if (line.trim())
                    this.emit("log", { level: "error", scope: "agent", message: line.trim() });
            }
        });
        child.on("error", (e) => {
            this.lastError = e.message;
            this.emit("log", { level: "error", scope: "agent", message: `falha ao iniciar agente: ${e.message}` });
            this.emit("status", this.status());
        });
        child.on("exit", (code, signal) => {
            const uptimeSec = Math.round((Date.now() - this.startedAt) / 1000);
            const msg = this.stopping
                ? `agente encerrado (uptime ${uptimeSec}s)`
                : `agente saíu inesperadamente — code=${code ?? "?"} signal=${signal ?? "?"} (uptime ${uptimeSec}s)`;
            this.emit("log", { level: this.stopping ? "info" : "error", scope: "agent", message: msg });
            this.child = null;
            this.rejectAllPending("agente não está mais rodando");
            this.emit("status", this.status());
        });
    }
    /** Encerra graciosamente (shutdown via protocolo, kill como fallback). */
    async stop() {
        if (!this.running)
            return;
        this.stopping = true;
        try {
            await this.request("shutdown", {}, 3000);
        }
        catch {
            // protocolo falhou — mata direto
        }
        const child = this.child;
        if (child && child.exitCode === null) {
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
        }
        this.child = null;
        this.emit("status", this.status());
    }
    /** Envia um comando e aguarda a resposta correspondente (por id). */
    async request(cmd, params = {}, timeoutMs) {
        if (!this.running)
            throw new Error("agente não está rodando — inicie em Dashboard/Configurações");
        const child = this.child;
        const id = String(this.nextId++);
        const timeout = timeoutMs ?? this.opts.requestTimeoutMs ?? 60_000;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                this.pending.delete(id);
                reject(new Error(`timeout (${Math.round(timeout / 1000)}s) no comando "${cmd}"`));
            }, timeout);
            this.pending.set(id, {
                resolve: (value) => {
                    clearTimeout(timer);
                    resolve(value);
                },
                timer,
            });
            child.stdin.write(`${JSON.stringify({ id, cmd, params })}\n`);
        });
    }
    /** Conveniências tipadas para a UI. */
    listIntegrations(includeInactive = false) {
        return this.request("listIntegrations", { includeInactive });
    }
    /** sync pode demorar minutos — timeout alto; outcomes chegam via evento. */
    sync(integrationId) {
        return this.request("sync", integrationId ? { integrationId } : {}, 10 * 60_000);
    }
    onStdout(chunk) {
        this.stdoutBuffer += chunk;
        let idx;
        while ((idx = this.stdoutBuffer.indexOf("\n")) !== -1) {
            const line = this.stdoutBuffer.slice(0, idx).trim();
            this.stdoutBuffer = this.stdoutBuffer.slice(idx + 1);
            if (line)
                this.handleLine(line);
        }
    }
    handleLine(line) {
        let parsed;
        try {
            parsed = JSON.parse(line);
        }
        catch {
            // stdout fora do protocolo (ex.: warning de lib) — trata como log.
            this.emit("log", { level: "info", scope: "agent", message: line });
            return;
        }
        if ("event" in parsed) {
            if (parsed.event === "ready") {
                this.emit("agent-ready");
                this.emit("log", { level: "info", scope: "agent", message: "subprocesso pronto (modo IPC)" });
            }
            else if (parsed.event === "log") {
                this.emit("log", { level: parsed.level, scope: "agent", message: parsed.message });
            }
            else if (parsed.event === "outcome") {
                this.emit("outcome", parsed.outcome);
            }
            return;
        }
        const pending = this.pending.get(parsed.id);
        if (pending) {
            this.pending.delete(parsed.id);
            pending.resolve(parsed.ok ? { ok: true, data: parsed.data } : { ok: false, error: parsed.error });
        }
    }
    rejectAllPending(reason) {
        for (const [id, p] of this.pending) {
            clearTimeout(p.timer);
            p.resolve({ ok: false, error: reason });
            this.pending.delete(id);
        }
    }
}
exports.AgentBridge = AgentBridge;
//# sourceMappingURL=agent-bridge.js.map
