// @ts-nocheck
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * relay-client — conexão outbound do desktop com o relay na nuvem
 * (App do Entregador — Fase 1 do roadmap).
 *
 * O desktop INICIA a conexão (WebSocket outbound — não precisa abrir porta
 * nem ter IP público). O relay repassa eventos `driver:location` do mobile;
 * aqui cada evento vira um callback registrado (onLocation/onStatus), que o
 * index.ts liga no event bus de realtime do backend (mesma UI de mapa).
 *
 * Reconexão: backoff exponencial 1s→2s→…→cap 60s, reiniciando a cada
 * conexão bem-sucedida. Todas as dependências de rede são injetáveis
 * (WebSocket, timers) para os testes rodarem sem rede real.
 */
const RECONNECT_BASE_MS = 1000;
const RECONNECT_CAP_MS = 60_000;
class RelayClient {
    constructor(deps) {
        this.deps = deps;
        this.relayUrl = deps.relayUrl || "";
        this.tenantId = deps.tenantId || "default";
        this.token = deps.token || "";
        this.WebSocketImpl = deps.WebSocketImpl || (typeof WebSocket !== "undefined" ? WebSocket : null);
        this.onLocation = deps.onLocation || null; // ({driver_id, lat, lng, ...})
        this.onStatus = deps.onStatus || null; // ("connected" | "disconnected")
        this.log = deps.log || (() => undefined);
        this.sleep = deps.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
        this.ws = null;
        this.stopped = true;
        this.attempt = 0;
    }
    get online() {
        return this.ws !== null && this.ws.readyState === 1; // OPEN
    }
    /** Conecta e mantém a conexão com reconexão automática. */
    start() {
        if (!this.relayUrl || !this.WebSocketImpl) {
            this.log("relay", "relay desabilitado (URL ou WebSocket ausente)");
            return;
        }
        if (!this.stopped)
            return;
        this.stopped = false;
        void this.loop();
    }
    stop() {
        this.stopped = true;
        if (this.ws) {
            try {
                this.ws.close();
            }
            catch { /* já fechado */ }
            this.ws = null;
        }
    }
    async loop() {
        while (!this.stopped) {
            try {
                await this.connectOnce();
                if (this.stopped)
                    return;
                const backoff = Math.min(RECONNECT_BASE_MS * Math.pow(2, this.attempt), RECONNECT_CAP_MS);
                this.attempt += 1;
                this.log("relay", `reconectando em ${backoff}ms (tentativa ${this.attempt})`);
                await this.sleep(backoff);
            }
            catch (e) {
                // connectOnce rejeita em erro de conexão — mesma rota do backoff
                this.log("relay", `falha de conexão: ${e.message}`);
                if (this.stopped)
                    return;
                const backoff = Math.min(RECONNECT_BASE_MS * Math.pow(2, this.attempt), RECONNECT_CAP_MS);
                this.attempt += 1;
                await this.sleep(backoff);
            }
        }
    }
    connectOnce() {
        return new Promise((resolve, reject) => {
            const url = `${this.relayUrl.replace(/\/+$/, "")}/relay/ws?tenant=${encodeURIComponent(this.tenantId)}&token=${encodeURIComponent(this.token)}`;
            let ws;
            try {
                ws = new this.WebSocketImpl(url);
            }
            catch (e) {
                reject(e);
                return;
            }
            this.ws = ws;
            const timeout = setTimeout(() => {
                try {
                    ws.close();
                }
                catch { /* noop */ }
                reject(new Error("timeout conectando ao relay"));
            }, 10_000);
            ws.onopen = () => {
                clearTimeout(timeout);
                this.attempt = 0; // conexão OK → zera backoff
                if (this.onStatus)
                    this.onStatus("connected");
                this.log("relay", "conectado ao relay");
                resolve();
            };
            ws.onmessage = (evt) => {
                try {
                    const data = JSON.parse(typeof evt.data === "string" ? evt.data : "");
                    if (data.type === "driver:location" && this.onLocation) {
                        this.onLocation(data.payload);
                    }
                    if (data.type === "driver:status" && this.onStatus) {
                        this.onStatus(data.payload);
                    }
                }
                catch {
                    this.log("relay", "mensagem inválida do relay (ignorada)");
                }
            };
            ws.onclose = () => {
                clearTimeout(timeout);
                if (this.onStatus && !this.stopped)
                    this.onStatus("disconnected");
                if (!this.stopped) {
                    // loop() resolve/rejeita via open/timeout; close inesperado
                    // precisa sinalizar o fim desta tentativa.
                    if (this.ws === ws)
                        this.ws = null;
                    reject(new Error("conexão fechada"));
                }
            };
            ws.onerror = () => { };
        });
    }
}
Object.defineProperty(exports, "__esModule", { value: true });
exports.RelayClient = RelayClient;
exports.RECONNECT_BASE_MS = RECONNECT_BASE_MS;
exports.RECONNECT_CAP_MS = RECONNECT_CAP_MS;
//# sourceMappingURL=relay-client.js.map