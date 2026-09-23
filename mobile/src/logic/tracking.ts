/**
 * tracking — serviço de rastreamento do App do Entregador (F2.5).
 *
 * Gate (decisão B2 — mesma semântica do desktop, DriverHomePage):
 *   - LIGA sozinho quando existe entrega em rota (ASSIGNED/DISPATCHED/EN_ROUTE)
 *   - DESLIGA sozinho quando a rota termina (override manual é limpo —
 *     a próxima rota religa sozinha)
 *   - Override manual respeitado: desligar com rota ativa mantém desligado
 *     ("desligado por você"); ligar manualmente antecipa o rastreio
 *   - Work-hours LGPD: fora da janela NADA é capturado (fail-closed) — vence
 *     até o override manual (o backend 403-aria de qualquer forma)
 *
 * Captura: watchPosition é INJETADO (cola nativa em containers/wired.tsx —
 * @react-native-community/geolocation); aqui vive só o CONTROLE (gate,
 * cadência, roteamento de envio, fila).
 *
 * Envio pelo canal ativo (connection.ts):
 *   - lan    → POST /driver/location (JWT do entregador; throttle 10s
 *              e work-hours reforçados no servidor)
 *   - cloud  → POST {relay}/driver/location (X-Relay-Token; relay é pipe
 *              burro — backend valida driver/tenant/audit)
 *   - offline→ OfflineQueue (kind "location") — replay no próximo flush
 *
 * Cadência: intervalo do /driver/me (driver.tracking.interval_seconds,
 * default 120s, min 15). Timestamp do servidor é autoritativo (anti
 * relógio-furado) — recorded_at vai só para ordenar.
 *
 * Módulo puro: fetch, relógio, watch e fila injetados — testável via
 * node --test, sem toolchain RN.
 */

// Imports com extensão .ts: o módulo roda também em node --test (type
// stripping nativo), onde imports sem extensão não resolvem.
// tsconfig: allowImportingTsExtensions=true, então o tsc aceita.
import { isWithinWorkHours, type WorkWindow } from "./workHours.ts";
import type { ResolvedConnection } from "./connection.ts";
import { postDriverLocation, postDriverLocationRelay } from "./api.ts";
import type { OfflineQueue } from "./offlineQueue.ts";

// ── Gate (decisão B2) ───────────────────────────────────────

export const ROUTING_STATUSES = ["ASSIGNED", "DISPATCHED", "EN_ROUTE"] as const;

export type TrackingPhase = "waiting" | "active" | "paused" | "disabled";
export type GateReason = "no_route" | "manual_off" | "out_of_hours";

export interface GateDecision {
  tracking: boolean;
  phase: TrackingPhase;
  reason?: GateReason;
  /** Existe entrega em rota? (o override manual é limpo quando a rota acaba) */
  onRoute: boolean;
}

export interface GateInput {
  statuses: readonly string[];
  /** null = sem preferência (automático); true/false = vontade explícita. */
  override: boolean | null;
  workWindow: string | WorkWindow | null | undefined;
  now: Date;
}

export function evaluateGate({ statuses, override, workWindow, now }: GateInput): GateDecision {
  const onRoute = statuses.some((s) => (ROUTING_STATUSES as readonly string[]).includes(s));
  if (override === false) return { tracking: false, phase: "paused", reason: "manual_off", onRoute };
  // LGPD vence tudo — nem o override manual captura fora da janela.
  if (!isWithinWorkHours(now, workWindow)) {
    return { tracking: false, phase: "disabled", reason: "out_of_hours", onRoute };
  }
  if (!onRoute && override !== true) {
    return { tracking: false, phase: "waiting", reason: "no_route", onRoute };
  }
  return { tracking: true, phase: "active", onRoute };
}

// ── Cadência ────────────────────────────────────────────────

export const DEFAULT_TRACKING_INTERVAL_SECONDS = 120;
export const MIN_TRACKING_INTERVAL_SECONDS = 15;

export function normalizeInterval(seconds: number | null | undefined): number {
  const n = Math.floor(Number(seconds));
  if (!Number.isFinite(n)) return DEFAULT_TRACKING_INTERVAL_SECONDS;
  return Math.max(MIN_TRACKING_INTERVAL_SECONDS, n);
}

export function shouldSendNow(lastSentAt: number | null, now: number, intervalSeconds: number): boolean {
  if (lastSentAt === null) return true;
  return now - lastSentAt >= normalizeInterval(intervalSeconds) * 1000;
}

// ── Posição e envio ─────────────────────────────────────────

export interface GpsPosition {
  latitude: number;
  longitude: number;
  accuracy?: number;
  speed?: number;
  bearing?: number;
  /** Epoch ms da captura (device) — só para ordenar; o servidor grava o próprio. */
  timestamp?: number;
}

export interface SendContext {
  connection: ResolvedConnection;
  token: string; // JWT do entregador (LAN)
  relayToken: string; // X-Relay-Token (nuvem)
  driverId: string;
  tenantId: string;
}

export type SendVia = "lan" | "cloud" | "queued";

/**
 * Envia uma posição pelo canal ativo. Sem canal (offline) devolve "queued" —
 * quem chama enfileira. Falha de rede LANÇA (quem chama decide a fila).
 */
export async function sendPosition(
  fetchFn: typeof fetch,
  ctx: SendContext,
  pos: GpsPosition,
): Promise<SendVia> {
  const { connection } = ctx;
  if (connection.mode === "lan" && connection.baseUrl && ctx.token) {
    await postDriverLocation(fetchFn, connection.baseUrl, ctx.token, {
      latitude: pos.latitude,
      longitude: pos.longitude,
      accuracy: pos.accuracy,
      speed: pos.speed,
      bearing: pos.bearing,
    });
    return "lan";
  }
  if (connection.mode === "cloud" && connection.baseUrl && ctx.relayToken) {
    await postDriverLocationRelay(fetchFn, connection.baseUrl, ctx.relayToken, {
      driverId: ctx.driverId,
      tenantId: ctx.tenantId,
      positions: [
        {
          lat: pos.latitude,
          lng: pos.longitude,
          speed: pos.speed ?? null,
          heading: pos.bearing ?? null,
          accuracy: pos.accuracy ?? null,
          recorded_at: new Date(pos.timestamp ?? Date.now()).toISOString(),
        },
      ],
    });
    return "cloud";
  }
  return "queued";
}

// ── Controller ──────────────────────────────────────────────

export interface TrackingSnapshot {
  statuses: readonly string[];
  workWindow: string | WorkWindow | null;
  intervalSeconds: number;
  token: string;
  relayToken: string;
  driverId: string;
  tenantId: string;
  connection: ResolvedConnection;
}

export interface TrackingDeps {
  fetchFn: typeof fetch;
  /** Epoch ms — injetável para os testes. */
  now: () => number;
  log?: (level: "info" | "warn", message: string) => void;
  getSnapshot: () => TrackingSnapshot;
  /** Captura nativa injetada (geolocation). Retorna a função de stop. */
  watch: (onPosition: (pos: GpsPosition) => void, onError: (e: Error) => void) => () => void;
  /** Fila offline para posições sem canal (kind "location"). */
  queue?: OfflineQueue;
}

export interface TrackingStatus {
  phase: TrackingPhase;
  reason?: GateReason;
  lastSentAt: number | null;
  lastError: string | null;
}

function errMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export class TrackingController {
  private deps: TrackingDeps;
  private override: boolean | null = null;
  private stopWatch: (() => void) | null = null;
  private lastPosition: GpsPosition | null = null;
  private lastSentAt: number | null = null;
  private lastError: string | null = null;
  private phase: TrackingPhase = "waiting";
  private reason?: GateReason;
  private lastDecision: GateDecision | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private running = false;

  constructor(deps: TrackingDeps) {
    this.deps = deps;
  }

  /** Vontade explícita do entregador (toggle manual). null = automático. */
  setOverride(on: boolean | null): void {
    this.override = on;
  }

  getOverride(): boolean | null {
    return this.override;
  }

  getStatus(): TrackingStatus {
    return { phase: this.phase, reason: this.reason, lastSentAt: this.lastSentAt, lastError: this.lastError };
  }

  /** Loop de controle (5s default — barato: só avalia o gate). */
  start(tickMs = 5000): void {
    if (this.running) return;
    this.running = true;
    const loop = async () => {
      if (!this.running) return;
      try {
        await this.tickOnce();
      } catch (e) {
        this.deps.log?.("warn", `tracking: tick falhou (${errMessage(e)})`);
      }
      this.timer = setTimeout(() => void loop(), tickMs);
    };
    void loop();
  }

  stop(): void {
    this.running = false;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.stopCapture();
  }

  /** Um ciclo de avaliação+envio — público para os testes (sem timers reais). */
  async tickOnce(): Promise<void> {
    const snap = this.deps.getSnapshot();
    const decision = evaluateGate({
      statuses: snap.statuses,
      override: this.override,
      workWindow: snap.workWindow,
      now: new Date(this.deps.now()),
    });
    this.lastDecision = decision;
    this.phase = decision.phase;
    this.reason = decision.reason;

    if (decision.tracking) {
      if (!this.stopWatch) {
        this.stopWatch = this.deps.watch(
          (pos) => {
            this.lastPosition = pos;
          },
          (e) => {
            this.lastError = e.message;
            this.deps.log?.("warn", `tracking: GPS (${e.message})`);
          },
        );
        this.deps.log?.("info", "tracking: captura ligada");
      }
      if (this.lastPosition && shouldSendNow(this.lastSentAt, this.deps.now(), snap.intervalSeconds)) {
        await this.send(this.lastPosition, snap);
      }
      return;
    }

    // Fora de rastreio: zero captura (bateria + LGPD).
    this.stopCapture();
  }

  private stopCapture(): void {
    if (this.stopWatch) {
      try {
        this.stopWatch();
      } catch {
        /* já parado */
      }
      this.stopWatch = null;
      this.lastPosition = null; // sem captura ⇒ nada pendente de envio
      this.deps.log?.("info", "tracking: captura desligada");
    }
    // A rota acabou (com ou sem vontade manual pendente) ⇒ override é limpo,
    // igual ao desktop — a PRÓXIMA rota religa sozinho. Enquanto a rota está
    // ativa, a vontade manual é preservada (nunca religa contra o entregador).
    if (this.lastDecision && !this.lastDecision.onRoute) this.override = null;
  }

  private async send(pos: GpsPosition, snap: TrackingSnapshot): Promise<void> {
    try {
      const via = await sendPosition(this.deps.fetchFn, {
        connection: snap.connection,
        token: snap.token,
        relayToken: snap.relayToken,
        driverId: snap.driverId,
        tenantId: snap.tenantId,
      }, pos);
      if (via === "queued") {
        this.enqueue(pos);
        return;
      }
      this.lastSentAt = this.deps.now();
      this.lastError = null;
    } catch (e) {
      this.lastError = errMessage(e);
      this.enqueue(pos);
      this.deps.log?.("warn", `tracking: envio falhou (${this.lastError}) — posição na fila`);
    }
  }

  /** Enfileira a posição (kind "location"); a cadência vale também para a fila. */
  private enqueue(pos: GpsPosition): void {
    this.lastSentAt = this.deps.now();
    if (!this.deps.queue) return; // sem fila injetada: descarta — próximo intervalo re-tenta
    this.deps.queue.enqueue("location", "", {
      latitude: pos.latitude,
      longitude: pos.longitude,
      accuracy: pos.accuracy,
      speed: pos.speed,
      bearing: pos.bearing,
      recorded_at: new Date(pos.timestamp ?? this.deps.now()).toISOString(),
    });
  }
}
