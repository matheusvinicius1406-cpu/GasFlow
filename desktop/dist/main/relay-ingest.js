// @ts-nocheck
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * relay-ingest — fecha o elo morto da cadeia do rastreador (App do
 * Entregador Fase 1 → rastreador em campo).
 *
 * Cadeia completa:
 *   Mobile (GPS, só em rota) ──HTTPS──▶ Relay (nuvem) ──WS──▶ Desktop
 *     ──POST /api/v1/internal/driver/location/relay──▶ backend embutido
 *     ──▶ driver_locations ──▶ mapa do operador (polling 30s)
 *
 * O POST direto do app (/api/v1/driver/location) só funciona na LAN.
 * Posições vindas da rua chegam ao desktop pelo relay; aqui elas são
 * ingestadas no backend com auth de máquina (X-GasFlow-Key — a mesma
 * chave injetada no backend no boot, settings.waApiKey), mesmo padrão
 * service-to-service do /whatsapp/incoming.
 *
 * Fire-and-forget: o relay-client já tem reconexão/backoff próprios;
 * falha de ingestão é log (warn), nunca derruba o desktop. Sem fila —
 * a próxima posição do mesmo entregador re-tenta naturalmente (120s).
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.IngestClient = void 0;
const node_http_1 = require("node:http");
class IngestClient {
    constructor(deps) {
        this.deps = deps;
        this.baseUrl = (deps.baseUrl || "").replace(/\/+$/, "");
        this.serviceKey = deps.serviceKey || "";
        this.tenantId = deps.tenantId || "default";
        this.log = deps.log || (() => undefined);
        this.HttpImpl = deps.HttpImpl || node_http_1.http;
    }
    /**
     * Ingesta um payload `driver:location` do relay no backend.
     * Payload: {driver_id, lat, lng, speed?, heading?, accuracy?, recorded_at?}.
     * POST única com o lote de 1 posição (o throttle de 10s do backend
     * deduplica; posições de mesmo driver em rajada ficam baratas).
     */
    ingestDriverLocation(payload) {
        if (!this.baseUrl || !this.serviceKey) {
            this.log("warn", "relay-ingest", "desabilitado (baseUrl ou service key ausente)");
            return;
        }
        const body = JSON.stringify({
            tenant_id: this.tenantId,
            driver_id: payload.driver_id,
            positions: [payload],
        });
        const req = this.HttpImpl.request(`${this.baseUrl}/api/v1/internal/driver/location/relay`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(body),
                "X-GasFlow-Key": this.serviceKey,
            },
            agent: false, // sem keep-alive — 1 request/120s por driver
            timeout: 5000,
        }, (res) => {
            res.resume(); // drena o body para liberar o socket
            if (res.statusCode && res.statusCode >= 400) {
                this.log("warn", "relay-ingest", `ingest falhou: HTTP ${res.statusCode}`);
            }
        });
        req.on("timeout", () => req.destroy(new Error("timeout no ingest de posição")));
        req.on("error", (e) => this.log("warn", "relay-ingest", `ingest falhou: ${e.message}`));
        req.end(body);
    }
}
exports.IngestClient = IngestClient;
//# sourceMappingURL=relay-ingest.js.map
