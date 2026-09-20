"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ServiceOrchestrator = void 0;
const DEFAULT_HEALTH_MS = 15_000;
const DEFAULT_BACKOFF_BASE = 2_000;
const DEFAULT_BACKOFF_MAX = 60_000;
const DEFAULT_MAX_FAILURES = 5;
class ServiceOrchestrator {
    services = new Map();
    persistencePath = null;
    stopped = false;
    /** Caminho opcional para persistir o estado de saúde (JSON). */
    setPersistence(path) {
        this.persistencePath = path;
    }
    register(spec) {
        if (this.services.has(spec.name)) {
            throw new Error(`serviço já registrado: ${spec.name}`);
        }
        this.services.set(spec.name, {
            spec,
            status: {
                name: spec.name,
                health: "stopped",
                attempts: 0,
                lastError: "",
                lastHealthyAt: null,
                restarts: 0,
                paused: false,
            },
            timer: null,
            backoffTimer: null,
            restarting: false,
        });
    }
    /** Sobe o serviço e inicia o loop de health (restart automático).
     * Falha no boot inicial NÃO aborta: o health loop assume e tenta
     * com backoff — serviço ausente no boot também precisa se recuperar. */
    async start(name) {
        const rt = this.services.get(name);
        if (!rt)
            throw new Error(`serviço desconhecido: ${name}`);
        this.stopped = false;
        rt.status.paused = false;
        rt.status.attempts = 0;
        try {
            await this.bringUp(rt);
        }
        catch {
            // boot falhou — o loop de health continua tentando (backoff)
        }
        this.startHealthLoop(rt);
    }
    /** Para o health loop e o serviço (shutdown do app). */
    async stop(name) {
        const rt = this.services.get(name);
        if (!rt)
            return;
        if (rt.timer)
            clearInterval(rt.timer);
        if (rt.backoffTimer)
            clearTimeout(rt.backoffTimer);
        rt.timer = null;
        rt.backoffTimer = null;
        rt.status.health = "stopped";
        try {
            await rt.spec.stop();
        }
        catch {
            /* best-effort no shutdown */
        }
    }
    async stopAll() {
        this.stopped = true;
        for (const name of this.services.keys()) {
            await this.stop(name);
        }
        this.persist();
    }
    /** Status de todos os serviços (para IPC/UI). */
    statusAll() {
        return [...this.services.values()].map((rt) => ({ ...rt.status }));
    }
    isHealthy(name) {
        const rt = this.services.get(name);
        return rt?.status.health === "healthy";
    }
    // ── Ciclo de vida ─────────────────────────────────────────
    async bringUp(rt) {
        if (rt.restarting)
            return;
        rt.restarting = true;
        rt.status.health = "starting";
        try {
            await rt.spec.stop();
        }
        catch {
            /* stop prévio best-effort (limpa processo zumbi) */
        }
        try {
            await rt.spec.start();
            // start() do spec é idempotente: se já está rodando, ok.
            const ok = await rt.spec.isHealthy().catch(() => false);
            if (ok) {
                const wasDown = rt.status.restarts > 0;
                rt.status.health = "healthy";
                rt.status.lastHealthyAt = Date.now();
                rt.status.lastError = "";
                if (wasDown) {
                    rt.spec.onEvent?.({
                        service: rt.spec.name,
                        type: "recovered",
                        detail: "serviço recuperado e saudável",
                        attempts: rt.status.attempts,
                    });
                }
                rt.status.attempts = 0;
                return;
            }
            throw new Error("health check falhou após start");
        }
        catch (e) {
            rt.status.health = "unhealthy";
            rt.status.lastError = e instanceof Error ? e.message : String(e);
            throw e;
        }
        finally {
            rt.restarting = false;
        }
    }
    startHealthLoop(rt) {
        const interval = rt.spec.healthIntervalMs ?? DEFAULT_HEALTH_MS;
        if (rt.timer)
            clearInterval(rt.timer);
        rt.timer = setInterval(() => {
            void this.checkOnce(rt);
        }, interval);
        // Não segura o processo vivo só por causa do timer.
        rt.timer.unref?.();
    }
    async checkOnce(rt) {
        if (rt.restarting || rt.status.paused || rt.status.health === "starting")
            return;
        let ok = false;
        try {
            ok = await rt.spec.isHealthy();
        }
        catch {
            ok = false;
        }
        if (ok) {
            if (rt.status.health !== "healthy") {
                rt.spec.onEvent?.({
                    service: rt.spec.name,
                    type: "recovered",
                    detail: "health check voltou a passar",
                    attempts: rt.status.attempts,
                });
            }
            rt.status.health = "healthy";
            rt.status.lastHealthyAt = Date.now();
            rt.status.attempts = 0;
            this.persist();
            return;
        }
        rt.status.health = "unhealthy";
        this.persist();
        await this.scheduleRestart(rt);
    }
    async scheduleRestart(rt) {
        if (rt.restarting || rt.status.paused)
            return;
        rt.status.attempts += 1;
        rt.status.restarts += 1;
        const max = rt.spec.maxConsecutiveFailures ?? DEFAULT_MAX_FAILURES;
        if (rt.status.attempts > max) {
            rt.status.paused = true;
            rt.status.health = "paused";
            // Cancela backoffs pendentes — nada roda enquanto pausado.
            if (rt.backoffTimer) {
                clearTimeout(rt.backoffTimer);
                rt.backoffTimer = null;
            }
            rt.spec.onEvent?.({
                service: rt.spec.name,
                type: "paused",
                detail: `${max} restarts seguidos falharam — restart pausado (serviço: ${rt.status.lastError})`,
                attempts: rt.status.attempts,
            });
            this.persist();
            return;
        }
        const base = rt.spec.backoffBaseMs ?? DEFAULT_BACKOFF_BASE;
        const maxMs = rt.spec.backoffMaxMs ?? DEFAULT_BACKOFF_MAX;
        const delay = Math.min(base * 2 ** (rt.status.attempts - 1), maxMs);
        rt.status.health = "backoff";
        rt.spec.onEvent?.({
            service: rt.spec.name,
            type: "unhealthy",
            detail: `restart em ${Math.round(delay / 1000)}s`,
            attempts: rt.status.attempts,
        });
        rt.backoffTimer = setTimeout(() => {
            rt.backoffTimer = null;
            void this.restartNow(rt);
        }, delay);
        rt.backoffTimer.unref?.();
    }
    async restartNow(rt) {
        if (rt.status.paused || this.stopped)
            return;
        try {
            await this.bringUp(rt);
            this.persist();
        }
        catch {
            // Falhou de novo — agenda próximo backoff (attempt++).
            await this.scheduleRestart(rt);
        }
    }
    /** Retoma manualmente um serviço pausado (botão do operador). */
    async resume(name) {
        const rt = this.services.get(name);
        if (!rt)
            throw new Error(`serviço desconhecido: ${name}`);
        rt.status.paused = false;
        rt.status.attempts = 0;
        rt.status.health = "stopped";
        await this.bringUp(rt);
        this.startHealthLoop(rt);
        this.persist();
    }
    // ── Persistência do estado de saúde ──────────────────────
    /** Salva o estado (último status por serviço) em JSON — best-effort. */
    persist() {
        if (!this.persistencePath)
            return;
        try {
            const fs = require("node:fs");
            const state = {
                savedAt: new Date().toISOString(),
                services: this.statusAll(),
            };
            fs.writeFileSync(this.persistencePath, JSON.stringify(state, null, 2), "utf-8");
        }
        catch {
            /* persistência é best-effort — nunca derruba o orquestrador */
        }
    }
    /** Estado persistido da última execução (para mostrar no boot). */
    loadPersisted() {
        if (!this.persistencePath)
            return null;
        try {
            const fs = require("node:fs");
            const raw = fs.readFileSync(this.persistencePath, "utf-8");
            const parsed = JSON.parse(raw);
            if (parsed && Array.isArray(parsed.services))
                return parsed;
        }
        catch {
            /* inexistente/corrompido → sem estado anterior */
        }
        return null;
    }
}
exports.ServiceOrchestrator = ServiceOrchestrator;
//# sourceMappingURL=orchestrator.js.map
