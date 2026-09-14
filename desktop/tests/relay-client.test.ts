/**
 * Testes do relay-client (App do Entregador — Fase 1): dist/main/relay-client.js
 * com WebSocket fake injetado — sem rede real. Cobre prompt 3.7:
 * conexão outbound, recebimento de driver:location e reconexão com backoff.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { createRequire } from "node:module";

const req = createRequire(__filename);
const { RelayClient } = req(path.resolve(__dirname, "../dist/main/relay-client.js"));

/** WebSocket fake controlado pelos testes. */
class FakeWebSocket {
    static instances: FakeWebSocket[] = [];
    static OPEN = 1;
    static CONNECTING = 0;
    static CLOSED = 3;
    readyState = 0;
    onopen: (() => void) | null = null;
    onmessage: ((evt: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    url: string;
    constructor(url: string) {
        this.url = url;
        FakeWebSocket.instances.push(this);
    }
    close() {
        this.readyState = 3;
    }
    emitOpen() {
        this.readyState = 1;
        this.onopen?.();
    }
    emitMessage(data: unknown) {
        this.onmessage?.({ data: JSON.stringify(data) });
    }
}

test("conecta, recebe driver:location e repassa ao callback", async () => {
    FakeWebSocket.instances = [];
    const received: unknown[] = [];
    const statuses: string[] = [];
    const client = new RelayClient({
        relayUrl: "https://relay.test",
        tenantId: "dep-1",
        token: "secret",
        WebSocketImpl: FakeWebSocket as unknown as new (url: string) => FakeWebSocket,
        onLocation: (p: unknown) => received.push(p),
        onStatus: (s: string) => statuses.push(s),
        sleep: async () => undefined,
    });
    client.start();
    await new Promise((r) => setTimeout(r, 5));
    const ws = FakeWebSocket.instances[0];
    ws.emitOpen();
    ws.emitMessage({ type: "driver:location", payload: { driver_id: "d1", lat: -1.45, lng: -48.49 } });

    assert.equal(ws.url.includes("tenant=dep-1"), true);
    assert.equal(ws.url.includes("token=secret"), true);
    assert.equal(received.length, 1);
    assert.deepEqual(received[0], { driver_id: "d1", lat: -1.45, lng: -48.49 });
    assert.ok(statuses.includes("connected"));
    client.stop();
});

test("reconexão usa backoff exponencial após fechamento", async () => {
    FakeWebSocket.instances = [];
    const sleeps: number[] = [];
    const client = new RelayClient({
        relayUrl: "https://relay.test",
        tenantId: "dep-1",
        token: "secret",
        WebSocketImpl: FakeWebSocket as unknown as new (url: string) => FakeWebSocket,
        sleep: async (ms: number) => {
            sleeps.push(ms);
        },
    });
    client.start();
    await new Promise((r) => setTimeout(r, 5));

    // 1ª tentativa falha (fecha sem abrir)
    let ws = FakeWebSocket.instances[0];
    ws.onclose?.();
    await new Promise((r) => setTimeout(r, 5));
    // 2ª tentativa falha também
    ws = FakeWebSocket.instances[1];
    ws.onclose?.();
    await new Promise((r) => setTimeout(r, 5));

    assert.deepEqual(sleeps, [1000, 2000], `backoff 1s→2s (obtido: ${sleeps.join(",")})`);
    client.stop();
});

test("start sem URL não conecta nada", () => {
    FakeWebSocket.instances = [];
    const client = new RelayClient({
        relayUrl: "",
        WebSocketImpl: FakeWebSocket as unknown as new (url: string) => FakeWebSocket,
    });
    client.start();
    assert.equal(FakeWebSocket.instances.length, 0);
});

test("stop encerra e não reconecta", async () => {
    FakeWebSocket.instances = [];
    const client = new RelayClient({
        relayUrl: "https://relay.test",
        tenantId: "dep-1",
        token: "secret",
        WebSocketImpl: FakeWebSocket as unknown as new (url: string) => FakeWebSocket,
        sleep: async () => undefined,
    });
    client.start();
    await new Promise((r) => setTimeout(r, 5));
    client.stop();
    const count = FakeWebSocket.instances.length;
    await new Promise((r) => setTimeout(r, 10));
    assert.equal(FakeWebSocket.instances.length, count, "nenhuma reconexão após stop");
    assert.equal(client.online, false);
});
