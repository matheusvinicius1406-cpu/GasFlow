/**
 * Testes do ServiceOrchestrator (F10.3): dist/main/orchestrator.js.
 * Cobre: start + health loop, restart com backoff em queda, recuperação,
 * pausa após excesso de falhas, resume manual e persistência de estado.
 * Serviços fake (sem rede, sem subprocessos); relógio controlado por
 * injeção — o orquestrador usa setInterval/setTimeout reais, então os
 * testes usam intervalos mínimos e awaits curtos (mesma estratégia dos
 * testes do relay-client).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { createRequire } from "node:module";

const req = createRequire(__filename);
const { ServiceOrchestrator } = req(path.resolve(__dirname, "../dist/main/orchestrator.js"));

/** Serviço fake: start/stop contam chamadas; isHealthy é controlável. */
function makeFakeService(name: string, opts: { healthy?: boolean; failStarts?: number } = {}) {
    let healthy = opts.healthy ?? true;
    let starts = 0;
    let stops = 0;
    let failStarts = opts.failStarts ?? 0;
    const events: { type: string; detail: string; attempts: number }[] = [];
    return {
        spec: {
            name,
            start: async () => {
                starts += 1;
                if (starts <= failStarts) throw new Error(`start falhou (${starts})`);
            },
            stop: async () => {
                stops += 1;
            },
            isHealthy: async () => healthy,
            healthIntervalMs: 20,
            backoffBaseMs: 10,
            backoffMaxMs: 40,
            maxConsecutiveFailures: 3,
            onEvent: (e: { type: string; detail: string; attempts: number }) => events.push(e),
        },
        setHealthy(v: boolean) {
            healthy = v;
        },
        /** Operador "conserta": próximas chamadas de start passam. */
        fixStarts() {
            failStarts = 0;
        },
        get starts() {
            return starts;
        },
        get stops() {
            return stops;
        },
        get events() {
            return events;
        },
    };
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

test("orquestrador: start saudável fica healthy e health loop detecta queda", async () => {
    const svc = makeFakeService("backend");
    const orch = new ServiceOrchestrator();
    orch.register(svc.spec);

    await orch.start("backend");
    assert.equal(orch.isHealthy("backend"), true);

    // Serviço cai → próximo tick do health loop detecta e agenda restart;
    // como o serviço continua "não saudável", bringUp lança e tenta de novo.
    svc.setHealthy(false);
    await wait(30);
    const st = orch.statusAll().find((s: { name: string }) => s.name === "backend");
    assert.ok(["backoff", "unhealthy", "starting"].includes(st.health));
    assert.ok(st.restarts >= 1);

    // Recupera → em até 2 ciclos volta a healthy
    svc.setHealthy(true);
    await wait(60);
    assert.equal(orch.isHealthy("backend"), true);

    await orch.stopAll();
});

test("orquestrador: reinicia serviço que caiu (stop externo) e registra restarts", async () => {
    const svc = makeFakeService("wa", { healthy: true });
    const orch = new ServiceOrchestrator();
    orch.register(svc.spec);
    await orch.start("wa");

    // Simula morte: health check passa a falhar; start volta a funcionar
    // (como um subprocesso que morreu e pode ser recriado).
    svc.setHealthy(false);
    await wait(25);
    svc.setHealthy(true);
    await wait(120);

    const st = orch.statusAll().find((s: { name: string }) => s.name === "wa");
    assert.equal(st.health, "healthy");
    assert.ok(st.restarts >= 1, "deve ter registrado ao menos 1 restart");
    const recovered = svc.events.find((e) => e.type === "recovered");
    assert.ok(recovered, "deve emitir evento recovered");

    await orch.stopAll();
});

test("orquestrador: pausa após excesso de falhas consecutivas e resume manual", async () => {
    const svc = makeFakeService("agent", { healthy: false, failStarts: 999 });
    const orch = new ServiceOrchestrator();
    orch.register(svc.spec);
    await orch.start("agent").catch(() => undefined); // start inicial falha é tolerado pelo loop

    await wait(200); // backoffs 10+20+40ms — 3 falhas → pausa
    let st = orch.statusAll().find((s: { name: string }) => s.name === "agent");
    assert.equal(st.paused, true);
    assert.equal(st.health, "paused");
    const pausedEvent = svc.events.find((e) => e.type === "paused");
    assert.ok(pausedEvent, "deve emitir evento paused");

    // Operador conserta o problema (start volta a funcionar) e resume
    svc.setHealthy(true);
    svc.fixStarts();
    await orch.resume("agent");
    st = orch.statusAll().find((s: { name: string }) => s.name === "agent");
    assert.equal(st.health, "healthy");
    assert.equal(st.paused, false);

    await orch.stopAll();
});

test("orquestrador: persistência guarda e recarrega estado por serviço", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "orch-"));
    const file = path.join(dir, "health-state.json");
    try {
        const svc = makeFakeService("assistant");
        const orch = new ServiceOrchestrator();
        orch.setPersistence(file);
        orch.register(svc.spec);
        await orch.start("assistant");
        orch.persist();

        assert.ok(fs.existsSync(file));
        const persisted = orch.loadPersisted();
        assert.ok(persisted);
        assert.equal(persisted.services[0].name, "assistant");
        assert.equal(persisted.services[0].health, "healthy");

        await orch.stopAll();
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("orquestrador: statusAll reflete registry completo", () => {
    const orch = new ServiceOrchestrator();
    orch.register(makeFakeService("a").spec);
    orch.register(makeFakeService("b").spec);
    const all = orch.statusAll();
    assert.equal(all.length, 2);
    assert.deepEqual(
        all.map((s: { name: string }) => s.name).sort(),
        ["a", "b"]
    );
});
