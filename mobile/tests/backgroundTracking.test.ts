/**
 * Fase 5 — adaptador de GPS em segundo plano (@ikolvi/tracelet).
 *
 * Testes com um fake da lib (nenhuma dependência de rede/device):
 * - config enviada à lib (distanceFilter ~20 m, HIGH, foreground service,
 *   lote 50, retenção 7 dias, autoSync só com URL)
 * - conversão Location → GpsPosition
 * - fallback de primeiro plano quando a lib falha ou não existe
 * - geofence por entrega (~150 m)
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_BACKGROUND_CONFIG,
  buildTraceletConfig,
  createBackgroundTracking,
  deliveryGeofence,
  toGpsPosition,
  type TraceletLike,
  type TraceletLocationLike,
} from "../src/logic/backgroundTracking.ts";
import type { GpsPosition } from "../src/logic/tracking.ts";

function makeTracelet(overrides: Partial<TraceletLike> = {}) {
  const calls = {
    ready: [] as unknown[],
    started: 0,
    stopped: 0,
    geofences: [] as unknown[],
    removed: 0,
  };
  let locationCb: ((l: TraceletLocationLike) => void) | null = null;

  const tracelet: TraceletLike = {
    ready: async (config) => {
      calls.ready.push(config);
      return {};
    },
    start: async () => {
      calls.started += 1;
      return {};
    },
    stop: async () => {
      calls.stopped += 1;
      return {};
    },
    onLocation: (cb) => {
      locationCb = cb;
      return { remove: () => (calls.removed += 1) };
    },
    addGeofence: async (g) => {
      calls.geofences.push(g);
      return true;
    },
    ...overrides,
  };

  return { tracelet, calls, emit: (l: TraceletLocationLike) => locationCb?.(l) };
}

describe("Fase 5 — buildTraceletConfig", () => {
  it("usa distanceFilter ~20m, precisão HIGH e foreground service", () => {
    const cfg = buildTraceletConfig();
    assert.equal(cfg.geo.distanceFilter, DEFAULT_BACKGROUND_CONFIG.distanceFilterM);
    assert.equal(cfg.geo.desiredAccuracy, "HIGH");
    assert.equal(cfg.app.foregroundService.enabled, true);
    assert.match(cfg.app.foregroundService.text, /Rastreamento ativo/);
  });

  it("lote de 50 e retenção de 7 dias", () => {
    const cfg = buildTraceletConfig();
    assert.equal(cfg.http.maxBatchSize, 50);
    assert.equal(cfg.http.maxDaysToPersist, 7);
    assert.equal(cfg.persistence.maxDaysToPersist, 7);
  });

  it("só liga autoSync quando há URL (offline não fica batendo na rede)", () => {
    assert.equal(buildTraceletConfig().http.autoSync, false);
    const withUrl = buildTraceletConfig({}, "https://example.test/driver/locations");
    assert.equal(withUrl.http.autoSync, true);
    assert.equal(withUrl.http.url, "https://example.test/driver/locations");
  });
});

describe("Fase 5 — toGpsPosition", () => {
  it("converte coords da lib no GpsPosition do controller", () => {
    const pos = toGpsPosition({
      coords: { latitude: -23.55, longitude: -46.63, accuracy: 8, speed: 12, heading: 90 },
      timestamp: "2026-09-22T12:00:00Z",
    });
    assert.equal(pos.latitude, -23.55);
    assert.equal(pos.bearing, 90);
    assert.equal(pos.timestamp, Date.parse("2026-09-22T12:00:00Z"));
  });

  it("ignora timestamp inválido", () => {
    assert.equal(toGpsPosition({ coords: { latitude: 1, longitude: 2 }, timestamp: "nope" }).timestamp, undefined);
  });
});

describe("Fase 5 — deliveryGeofence", () => {
  it("cria o fence da entrega com ~150m e sem auto-conclusão", () => {
    const fence = deliveryGeofence({ id: "d1", latitude: -23.55, longitude: -46.63 });
    assert.equal(fence.identifier, "delivery:d1");
    assert.equal(fence.radius, 150);
    assert.equal(fence.notifyOnEntry, true);
    assert.equal(fence.notifyOnExit, false);
  });
});

describe("Fase 5 — adaptador", () => {
  it("sem a lib, cai no fallback de primeiro plano", () => {
    let fallbackUsed = 0;
    const handle = createBackgroundTracking({
      tracelet: null,
      fallback: () => {
        fallbackUsed += 1;
        return () => undefined;
      },
    });

    assert.equal(handle.isBackground, false);
    const stop = handle.watch(
      () => undefined,
      () => undefined,
    );
    assert.equal(fallbackUsed, 1);
    stop();
  });

  it("com a lib, liga background e entrega as posições convertidas", async () => {
    const { tracelet, calls, emit } = makeTracelet();
    const handle = createBackgroundTracking({ tracelet, fallback: () => () => undefined });
    assert.equal(handle.isBackground, true);

    const received: GpsPosition[] = [];
    handle.watch(
      (p) => received.push(p),
      () => undefined,
    );

    await new Promise((r) => setTimeout(r, 0));
    assert.equal(calls.ready.length, 1);
    assert.equal(calls.started, 1);

    emit({ coords: { latitude: -23.5, longitude: -46.6 } });
    assert.equal(received.length, 1);
    assert.equal(received[0]!.latitude, -23.5);
  });

  it("para a lib e remove a subscription ao parar a captura", async () => {
    const { tracelet, calls } = makeTracelet();
    const handle = createBackgroundTracking({ tracelet, fallback: () => () => undefined });

    const stop = handle.watch(
      () => undefined,
      () => undefined,
    );
    await new Promise((r) => setTimeout(r, 0));
    stop();
    await new Promise((r) => setTimeout(r, 0));

    assert.equal(calls.removed, 1);
    assert.equal(calls.stopped >= 1, true);
  });

  it("se a lib falha, cai no fallback em vez de ficar sem rastreio", async () => {
    const { tracelet } = makeTracelet({
      ready: async () => {
        throw new Error("native module missing");
      },
    });
    let fallbackUsed = 0;
    const errors: Error[] = [];
    const handle = createBackgroundTracking({
      tracelet,
      fallback: () => {
        fallbackUsed += 1;
        return () => undefined;
      },
    });

    handle.watch(
      () => undefined,
      (e) => errors.push(e),
    );
    await new Promise((r) => setTimeout(r, 0));

    assert.equal(errors.length, 1);
    assert.equal(fallbackUsed, 1);
  });

  it("registra o geofence da entrega", async () => {
    const { tracelet, calls } = makeTracelet();
    const handle = createBackgroundTracking({ tracelet, fallback: () => () => undefined });

    const ok = await handle.addDeliveryGeofence({ id: "d9", latitude: -23.5, longitude: -46.6 });

    assert.equal(ok, true);
    assert.equal((calls.geofences[0] as { identifier: string }).identifier, "delivery:d9");
  });

  it("sem a lib, o geofence é recusado (sem crash)", async () => {
    const handle = createBackgroundTracking({ tracelet: null, fallback: () => () => undefined });
    assert.equal(await handle.addDeliveryGeofence({ id: "d1", latitude: 1, longitude: 2 }), false);
  });
});
