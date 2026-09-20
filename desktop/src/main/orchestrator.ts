"use strict";
/**
 * ServiceOrchestrator — F10.3
 *
 * Mantém TODOS os serviços vivos enquanto o app estiver aberto:
 * desired-state loop com health checks periódicos, restart com backoff
 * exponencial (teto), pausa por excesso de falhas (evita crash-loop sem
 * fim), notificação ao operador e persistência do estado de saúde entre
 * reinícios do Electron (degradação notória em vez de silenciosa).
 *
 * Serviços são declarados via ServiceSpec — spawn/stop/health ficam com
 * o chamador (index.ts), o orquestrador é puro ciclo de vida + política.
 */

export type ServiceHealth = "stopped" | "starting" | "healthy" | "unhealthy" | "backoff" | "paused";

export interface ServiceSpec {
    /** Identificador estável (backend, whatsapp, agent, assistant). */
    name: string;
    /** Sobe o serviço (idempotente). */
    start: () => Promise<void>;
    /** Para o serviço (idempotente, best-effort). */
    stop: () => Promise<void>;
    /** Health check pontual: true = saudável. */
    isHealthy: () => Promise<boolean>;
    /** Intervalo do health check em ms (default 15s). */
    healthIntervalMs?: number;
    /** Backoff inicial de restart em ms (default 2s). */
    backoffBaseMs?: number;
    /** Teto do backoff em ms (default 60s). */
    backoffMaxMs?: number;
    /** Falhas consecutivas antes de pausar o restart (default 5). */
    maxConsecutiveFailures?: number;
    /** Chamado em transições relevantes (para Notification/toast). */
    onEvent?: (event: OrchestratorEvent) => void;
}

export interface OrchestratorEvent {
    service: string;
    type: "restarted" | "unhealthy" | "paused" | "recovered";
    detail: string;
    attempts: number;
}

export interface ServiceStatus {
    name: string;
    health: ServiceHealth;
    attempts: number;
    lastError: string;
    lastHealthyAt: number | null;
    restarts: number;
    paused: boolean;
}

interface Runtime {
    spec: ServiceSpec;
    status: ServiceStatus;
    timer: ReturnType<typeof setInterval> | null;
    backoffTimer: ReturnType<typeof setTimeout> | null;
    restarting: boolean;
}

const DEFAULT_HEALTH_MS = 15_000;
const DEFAULT_BACKOFF_BASE = 2_000;
const DEFAULT_BACKOFF_MAX = 60_000;
const DEFAULT_MAX_FAILURES = 5;

export class ServiceOrchestrator {
    private services = new Map<string, Runtime>();
    private persistencePath: string | null = null;
    private stopped = false;

    /** Caminho opcional para persistir o estado de saúde (JSON). */
    setPersistence(path: string): void {
        this.persistencePath = path;
    }

    register(spec: ServiceSpec): void {
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
    async start(name: string): Promise<void> {
        const rt = this.services.get(name);
        if (!rt) throw new Error(`serviço desconhecido: ${name}`);
        this.stopped = false;
        rt.status.paused = false;
        rt.status.attempts = 0;
        try {
            await this.bringUp(rt);
        } catch {
            // boot falhou — o loop de health continua tentando (backoff)
        }
        this.startHealthLoop(rt);
    }

    /** Para o health loop e o serviço (shutdown do app). */
    async stop(name: string): Promise<void> {
        const rt = this.services.get(name);
        if (!rt) return;
        if (rt.timer) clearInterval(rt.timer);
        if (rt.backoffTimer) clearTimeout(rt.backoffTimer);
        rt.timer = null;
        rt.backoffTimer = null;
        rt.status.health = "stopped";
        try {
            await rt.spec.stop();
        } catch {
            /* best-effort no shutdown */
        }
    }

    async stopAll(): Promise<void> {
        this.stopped = true;
        for (const name of this.services.keys()) {
            await this.stop(name);
        }
        this.persist();
    }

    /** Status de todos os serviços (para IPC/UI). */
    statusAll(): ServiceStatus[] {
        return [...this.services.values()].map((rt) => ({ ...rt.status }));
    }

    isHealthy(name: string): boolean {
        const rt = this.services.get(name);
        return rt?.status.health === "healthy";
    }

    // ── Ciclo de vida ─────────────────────────────────────────

    private async bringUp(rt: Runtime): Promise<void> {
        if (rt.restarting) return;
        rt.restarting = true;
        rt.status.health = "starting";
        try {
            await rt.spec.stop();
        } catch {
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
        } catch (e) {
            rt.status.health = "unhealthy";
            rt.status.lastError = e instanceof Error ? e.message : String(e);
            throw e;
        } finally {
            rt.restarting = false;
        }
    }

    private startHealthLoop(rt: Runtime): void {
        const interval = rt.spec.healthIntervalMs ?? DEFAULT_HEALTH_MS;
        if (rt.timer) clearInterval(rt.timer);
        rt.timer = setInterval(() => {
            void this.checkOnce(rt);
        }, interval);
        // Não segura o processo vivo só por causa do timer.
        rt.timer.unref?.();
    }

    private async checkOnce(rt: Runtime): Promise<void> {
        if (rt.restarting || rt.status.paused || rt.status.health === "starting") return;
        let ok = false;
        try {
            ok = await rt.spec.isHealthy();
        } catch {
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

    private async scheduleRestart(rt: Runtime): Promise<void> {
        if (rt.restarting || rt.status.paused) return;
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

    private async restartNow(rt: Runtime): Promise<void> {
        if (rt.status.paused || this.stopped) return;
        try {
            await this.bringUp(rt);
            this.persist();
        } catch {
            // Falhou de novo — agenda próximo backoff (attempt++).
            await this.scheduleRestart(rt);
        }
    }

    /** Retoma manualmente um serviço pausado (botão do operador). */
    async resume(name: string): Promise<void> {
        const rt = this.services.get(name);
        if (!rt) throw new Error(`serviço desconhecido: ${name}`);
        rt.status.paused = false;
        rt.status.attempts = 0;
        rt.status.health = "stopped";
        await this.bringUp(rt);
        this.startHealthLoop(rt);
        this.persist();
    }

    // ── Persistência do estado de saúde ──────────────────────

    /** Salva o estado (último status por serviço) em JSON — best-effort. */
    persist(): void {
        if (!this.persistencePath) return;
        try {
            const fs = require("node:fs");
            const state = {
                savedAt: new Date().toISOString(),
                services: this.statusAll(),
            };
            fs.writeFileSync(this.persistencePath, JSON.stringify(state, null, 2), "utf-8");
        } catch {
            /* persistência é best-effort — nunca derruba o orquestrador */
        }
    }

    /** Estado persistido da última execução (para mostrar no boot). */
    loadPersisted(): { savedAt: string; services: ServiceStatus[] } | null {
        if (!this.persistencePath) return null;
        try {
            const fs = require("node:fs");
            const raw = fs.readFileSync(this.persistencePath, "utf-8");
            const parsed = JSON.parse(raw);
            if (parsed && Array.isArray(parsed.services)) return parsed;
        } catch {
            /* inexistente/corrompido → sem estado anterior */
        }
        return null;
    }
}
