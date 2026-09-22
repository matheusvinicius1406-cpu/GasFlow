/**
 * backgroundTracking — adaptador de GPS em segundo plano (Fase 5).
 *
 * O `TrackingController` já recebe a captura por injeção (`watch`). Aqui vive
 * só a cola que troca a captura de primeiro plano por **background real**,
 * usando `@ikolvi/tracelet` (Apache-2.0, sem conta/API key). Nada do gate,
 * cadência ou fila muda: o controller continua sendo o único dono da política.
 *
 * Pontos importantes:
 * - A lib nativa é **opcional** (`deps.tracelet`). Sem ela — node --test, iOS
 *   sem pod, build que ainda não linkou — cai no `fallback` (comportamento
 *   atual, primeiro plano). O app nunca fica sem rastreio por causa disso.
 * - Config: `distanceFilter` ~20 m, precisão HIGH, **foreground service** com
 *   notificação persistente, autoSync (quando há URL) com lote de 50 e
 *   persistência local de 7 dias — exatamente o que o enunciado pede.
 * - Geofencing: 1 fence por entrega (~150 m do endereço). No ENTER apenas
 *   SUGERE "marcar como chegou" — nunca conclui sozinho.
 *
 * Módulo puro: nenhum import da lib em runtime (só tipos), então roda em
 * node --test com um fake injetado.
 */

import type { GpsPosition } from "./tracking.ts";

// ── Tipos mínimos da lib (evita acoplar o módulo ao pacote nativo) ──────────

export interface TraceletCoordsLike {
  latitude: number;
  longitude: number;
  accuracy?: number;
  speed?: number;
  heading?: number;
}

export interface TraceletLocationLike {
  coords: TraceletCoordsLike;
  timestamp?: string;
}

export interface TraceletSubscriptionLike {
  remove?: () => void;
}

export interface TraceletLike {
  ready(config: TraceletConfig): Promise<unknown>;
  start(): Promise<unknown>;
  stop(): Promise<unknown>;
  onLocation(callback: (location: TraceletLocationLike) => void): TraceletSubscriptionLike;
  addGeofence(geofence: TraceletGeofenceLike): Promise<boolean>;
}

export interface TraceletForegroundServiceConfig {
  enabled: boolean;
  title: string;
  text: string;
  channelName: string;
}

export interface TraceletConfig {
  geo: {
    desiredAccuracy: string;
    distanceFilter: number;
    locationUpdateInterval: number;
  };
  app: {
    stopOnTerminate: boolean;
    startOnBoot: boolean;
    foregroundService: TraceletForegroundServiceConfig;
  };
  http: {
    url?: string;
    method: string;
    autoSync: boolean;
    batchSync: boolean;
    maxBatchSize: number;
    maxDaysToPersist: number;
  };
  persistence: {
    maxDaysToPersist: number;
  };
}

export interface TraceletGeofenceLike {
  identifier: string;
  latitude: number;
  longitude: number;
  radius: number;
  notifyOnEntry: boolean;
  notifyOnExit: boolean;
  extras?: Record<string, unknown>;
}

// ── Configuração ────────────────────────────────────────────────────────────

export interface BackgroundTrackingConfig {
  /** Distância mínima entre capturas (m). Default 20. */
  distanceFilterM: number;
  /** Cadência de updates em segundo plano (s). Default 120 — igual ao /driver/me. */
  intervalSeconds: number;
  /** Tamanho do lote do autoSync. Default 50. */
  maxBatchSize: number;
  /** Retenção local (dias). Default 7. */
  retentionDays: number;
  notificationTitle: string;
  notificationText: string;
  channelName: string;
  /** Raio do geofence por entrega (m). Default 150. */
  geofenceRadiusM: number;
}

export const DEFAULT_BACKGROUND_CONFIG: BackgroundTrackingConfig = {
  distanceFilterM: 20,
  intervalSeconds: 120,
  maxBatchSize: 50,
  retentionDays: 7,
  notificationTitle: "GasFlow",
  notificationText: "Rastreamento ativo",
  channelName: "gasflow-tracking",
  geofenceRadiusM: 150,
};

/** Monta o `Config` da lib — função pura, para os testes conferirem o contrato. */
export function buildTraceletConfig(
  config: Partial<BackgroundTrackingConfig> = {},
  syncUrl?: string,
): TraceletConfig {
  const cfg = { ...DEFAULT_BACKGROUND_CONFIG, ...config };
  return {
    geo: {
      desiredAccuracy: "HIGH",
      distanceFilter: cfg.distanceFilterM,
      locationUpdateInterval: cfg.intervalSeconds * 1000,
    },
    app: {
      stopOnTerminate: false,
      startOnBoot: true,
      foregroundService: {
        enabled: true,
        title: cfg.notificationTitle,
        text: cfg.notificationText,
        channelName: cfg.channelName,
      },
    },
    http: {
      // autoSync só quando existe endpoint — sem URL, a lib apenas persiste
      // localmente e o app envia pelo canal ativo (LAN/relay/fila).
      ...(syncUrl ? { url: syncUrl } : {}),
      method: "POST",
      autoSync: Boolean(syncUrl),
      batchSync: Boolean(syncUrl),
      maxBatchSize: cfg.maxBatchSize,
      maxDaysToPersist: cfg.retentionDays,
    },
    persistence: {
      maxDaysToPersist: cfg.retentionDays,
    },
  };
}

/** Converte o `Location` da lib no `GpsPosition` do controller. */
export function toGpsPosition(location: TraceletLocationLike): GpsPosition {
  const ts = location.timestamp ? Date.parse(location.timestamp) : NaN;
  return {
    latitude: location.coords.latitude,
    longitude: location.coords.longitude,
    accuracy: location.coords.accuracy,
    speed: location.coords.speed,
    bearing: location.coords.heading,
    timestamp: Number.isFinite(ts) ? ts : undefined,
  };
}

/** Geofence de uma entrega (raio ~150 m do endereço). */
export function deliveryGeofence(
  delivery: { id: string; latitude: number; longitude: number },
  radiusM: number = DEFAULT_BACKGROUND_CONFIG.geofenceRadiusM,
): TraceletGeofenceLike {
  return {
    identifier: `delivery:${delivery.id}`,
    latitude: delivery.latitude,
    longitude: delivery.longitude,
    radius: radiusM,
    notifyOnEntry: true,
    notifyOnExit: false,
    extras: { deliveryId: delivery.id },
  };
}

// ── Adaptador ───────────────────────────────────────────────────────────────

export type ForegroundWatch = (
  onPosition: (pos: GpsPosition) => void,
  onError: (e: Error) => void,
) => () => void;

export interface BackgroundTrackingDeps {
  /** Lib nativa. `null`/ausente ⇒ usa o fallback de primeiro plano. */
  tracelet?: TraceletLike | null;
  /** Captura de primeiro plano já existente (geolocation). */
  fallback: ForegroundWatch;
  config?: Partial<BackgroundTrackingConfig>;
  /** Endpoint de autoSync da lib (opcional; normalmente vazio — ver acima). */
  syncUrl?: string;
  log?: (level: "info" | "warn", message: string) => void;
}

export interface BackgroundTrackingHandle {
  /** Substitui o `watch` injetado no TrackingController. */
  watch: ForegroundWatch;
  /** Registra o fence da entrega e retorna true quando aplicado. */
  addDeliveryGeofence(delivery: { id: string; latitude: number; longitude: number }): Promise<boolean>;
  /** Desliga a captura de background (sem tocar no fallback). */
  stop(): void;
  /** true quando a lib nativa está em uso. */
  readonly isBackground: boolean;
}

function toError(e: unknown): Error {
  return e instanceof Error ? e : new Error(String(e));
}

/**
 * Cria o adaptador. `watch` é síncrono (contrato do controller) — a
 * preparação assíncrona da lib acontece em background e, se falhar, o erro
 * vai para `onError` e cai no fallback de primeiro plano.
 */
export function createBackgroundTracking(deps: BackgroundTrackingDeps): BackgroundTrackingHandle {
  const tracelet = deps.tracelet ?? null;
  const bgConfig = { ...DEFAULT_BACKGROUND_CONFIG, ...deps.config };
  const config = buildTraceletConfig(bgConfig, deps.syncUrl);
  let stopped = false;
  let subscription: TraceletSubscriptionLike | null = null;

  const watch: ForegroundWatch = (onPosition, onError) => {
    if (!tracelet) {
      deps.log?.("info", "tracking: lib de background ausente — usando primeiro plano");
      return deps.fallback(onPosition, onError);
    }

    let localStop: (() => void) | null = null;
    void (async () => {
      try {
        await tracelet.ready(config);
        const sub = tracelet.onLocation((location) => {
          try {
            onPosition(toGpsPosition(location));
          } catch (e) {
            onError(toError(e));
          }
        });
        if (stopped) {
          sub.remove?.();
          return;
        }
        subscription = sub;
        await tracelet.start();
        deps.log?.("info", "tracking: background ligado (foreground service)");
      } catch (e) {
        const err = toError(e);
        deps.log?.("warn", `tracking: background falhou (${err.message}) — primeiro plano`);
        onError(err);
        // Fallback: mantém o rastreio vivo mesmo sem a lib nativa.
        if (!stopped) localStop = deps.fallback(onPosition, onError);
      }
    })();

    const stopFn = () => {
      localStop?.();
      localStop = null;
      subscription?.remove?.();
      subscription = null;
      void Promise.resolve()
        .then(() => tracelet.stop())
        .catch(() => undefined);
    };
    return stopFn;
  };

  return {
    watch,
    isBackground: Boolean(tracelet),
    async addDeliveryGeofence(delivery) {
      if (!tracelet) return false;
      try {
        return await tracelet.addGeofence(deliveryGeofence(delivery, bgConfig.geofenceRadiusM));
      } catch (e) {
        deps.log?.("warn", `tracking: geofence falhou (${toError(e).message})`);
        return false;
      }
    },
    stop() {
      stopped = true;
      subscription?.remove?.();
      subscription = null;
      if (tracelet) {
        void Promise.resolve()
          .then(() => tracelet.stop())
          .catch(() => undefined);
      }
    },
  };
}
