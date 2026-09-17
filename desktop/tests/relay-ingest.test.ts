/**
 * Testes do relay-ingest (Fix do elo morto do rastreador): dist/main/relay-ingest.js
 * com módulo http fake injetado — sem rede real. Cobre:
 * - POST em /api/v1/internal/driver/location/relay com X-GasFlow-Key
 * - payload do lote (tenant_id, driver_id, positions)
 * - desabilitado sem baseUrl/serviceKey (fail-safe, nunca crasha)
 * - erro de rede/HTTP >= 400 é log warn, não exceção (fire-and-forget)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { createRequire } from "node:module";

const req = createRequire(__filename);
const { IngestClient } = req(path.resolve(__dirname, "../dist/main/relay-ingest.js"));

/** http fake: captura request sem abrir socket. */
function makeFakeHttp(overrides: { statusCode?: number } = {}) {
    const calls: Array<{ url: string; options: any; body: string }> = [];
    const request = (url: string, options: any, callback: (res: any) => void) => {
        calls.push({ url, options, body: "" });
        const reqFake = {
            on(_evt: string, _cb: (e?: Error) => void) {
                return reqFake;
            },
            end(body: string) {
                calls[calls.length - 1].body = body;
                callback({ statusCode: overrides.statusCode ?? 200, resume() {} });
            },
            destroy(_e?: Error) {},
        };
        return reqFake;
    };
    return { fakeHttp: { request }, calls };
}

const PAYLOAD = { driver_id: "d1", lat: -1.4558, lng: -48.4902, speed: 30.5 };

test("POSTa o lote no endpoint interno com X-GasFlow-Key", () => {
    const { fakeHttp, calls } = makeFakeHttp();
    const logs: Array<[string, string, string]> = [];
    const client = new IngestClient({
        baseUrl: "http://127.0.0.1:8000/",
        serviceKey: "secret-key",
        tenantId: "dep-1",
        log: (level: string, scope: string, msg: string) => logs.push([level, scope, msg]),
        HttpImpl: fakeHttp,
    });

    client.ingestDriverLocation(PAYLOAD);

    assert.equal(calls.length, 1);
    const { url, options, body } = calls[0];
    assert.equal(url, "http://127.0.0.1:8000/api/v1/internal/driver/location/relay");
    assert.equal(options.method, "POST");
    assert.equal(options.headers["X-GasFlow-Key"], "secret-key");
    const parsed = JSON.parse(body);
    assert.equal(parsed.tenant_id, "dep-1");
    assert.equal(parsed.driver_id, "d1");
    assert.deepEqual(parsed.positions, [PAYLOAD]);
    // barra final da baseUrl normalizada (sem "//")
    assert.equal(url.includes("//api"), false);
});

test("desabilitado sem serviceKey — não faz request", () => {
    const { fakeHttp, calls } = makeFakeHttp();
    const logs: string[] = [];
    const client = new IngestClient({
        baseUrl: "http://127.0.0.1:8000",
        serviceKey: "",
        log: (_l: string, _s: string, msg: string) => logs.push(msg),
        HttpImpl: fakeHttp,
    });

    client.ingestDriverLocation(PAYLOAD);

    assert.equal(calls.length, 0);
    assert.ok(logs.some((m) => m.includes("desabilitado")));
});

test("HTTP 4xx do backend é warn, não exceção", () => {
    const { fakeHttp } = makeFakeHttp({ statusCode: 401 });
    const warns: string[] = [];
    const client = new IngestClient({
        baseUrl: "http://127.0.0.1:8000",
        serviceKey: "k",
        log: (level: string, _s: string, msg: string) => {
            if (level === "warn") warns.push(msg);
        },
        HttpImpl: fakeHttp,
    });

    assert.doesNotThrow(() => client.ingestDriverLocation(PAYLOAD));
    assert.ok(warns.some((m) => m.includes("401")));
});
