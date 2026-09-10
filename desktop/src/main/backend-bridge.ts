// @ts-nocheck
"use strict";
/**
 * BackendBridge — roda o backend FastAPI como subprocesso (uvicorn).
 *
 * O backend serve o frontend React original (FRONTEND_DIST) e as APIs sob
 * /api — o Electron vira container: janela carrega http://127.0.0.1:<porta>.
 *
 * Requisitos locais (dev): Python 3.11+ com as deps do backend instaladas
 * (`pip install -r requirements.txt`). Empacotado: PyInstaller (roadmap).
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.BackendBridge = void 0;
const node_child_process_1 = require("node:child_process");
class BackendBridge {
    opts;
    child = null;
    onLog;
    constructor(opts, onLog) {
        this.opts = opts;
        this.onLog = onLog;
    }
    get running() {
        return this.child !== null && this.child.exitCode === null;
    }
    status() {
        return { running: this.running, pid: this.child?.pid, url: this.opts.healthUrl.replace(/\/health$/, "") };
    }
    /** Inicia o uvicorn e aguarda GET /health responder. */
    async start() {
        if (this.running)
            return;
        const child = (0, node_child_process_1.spawn)(this.opts.command, this.opts.args, {
            cwd: this.opts.cwd,
            env: { ...process.env, ...this.opts.env },
            stdio: ["ignore", "pipe", "pipe"],
            windowsHide: true,
        });
        this.child = child;
        const forward = (buf, level) => {
            for (const line of buf.split(/\r?\n/)) {
                if (line.trim())
                    this.onLog(level, "backend", line.trim());
            }
        };
        child.stdout?.setEncoding("utf-8");
        child.stdout?.on("data", (d) => forward(d, "info"));
        child.stderr?.setEncoding("utf-8");
        child.stderr?.on("data", (d) => forward(d, "error"));
        child.on("error", (e) => this.onLog("error", "backend", `falha ao iniciar: ${e.message}`));
        child.on("exit", (code) => {
            this.child = null;
            this.onLog("info", "backend", `uvicorn encerrado (code=${code ?? "?"})`);
        });
        // Aguarda /health (primeira execução pode criar tabelas/migrar).
        const deadline = Date.now() + (this.opts.waitMs ?? 90_000);
        while (Date.now() < deadline) {
            if (!this.running) {
                throw new Error("backend saiu durante a inicialização — veja os logs (Python/deps instalados?)");
            }
            try {
                const res = await (this.opts.fetchFn ?? fetch)(this.opts.healthUrl, { signal: AbortSignal.timeout(2000) });
                if (res.ok)
                    return;
            }
            catch {
                /* ainda subindo */
            }
            await new Promise((r) => setTimeout(r, 500));
        }
        throw new Error("backend não respondeu /health a tempo");
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
            }, 5000);
            child.once("exit", () => {
                clearTimeout(timer);
                resolve();
            });
        });
    }
}
exports.BackendBridge = BackendBridge;
//# sourceMappingURL=backend-bridge.js.map
