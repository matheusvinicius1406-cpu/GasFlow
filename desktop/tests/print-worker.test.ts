/**
 * Testes do PrintWorker (F10.7): dist/main/print-worker.js.
 *
 * Sem rede e sem impressora: fetch e impressão são injetados. Cobre o ciclo
 * claim → impressão → resultado, a fila vazia, a impressora não configurada,
 * a falha de rede (não confundir backend fora com térmica fora), o dedupe do
 * relato de status e a saúde usada pelo orquestrador.
 *
 * Anti-duplicata e reconexão (F10.7): job devolvido à fila não sai de novo
 * (ledger em disco, sobrevive a restart), relato de status perdido é reenviado
 * e 401 tem diagnóstico próprio em vez de virar "backend fora".
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const req = createRequire(__filename);
const { PrintWorker } = req(path.resolve(__dirname, "../dist/main/print-worker.js"));

interface Call {
    url: string;
    method: string;
    body: unknown;
}

/** Backend fake: responde /next conforme a fila informada e grava tudo. */
function makeBackend(
    initialJobs: { id: string; order_id: string; escpos_base64: string }[] = [],
    expiredJobs = 0
) {
    const jobs = [...initialJobs];
    const calls: Call[] = [];
    const backend = { expiredJobs };
    const fetchFn = async (url: string, init: { method?: string; body?: string } = {}) => {
        calls.push({
            url: String(url),
            method: init.method ?? "GET",
            body: init.body ? JSON.parse(init.body) : undefined,
        });
        if (String(url).includes("/printer/agent/next")) {
            const job = jobs.shift() ?? null;
            return {
                ok: true,
                json: async () => ({
                    job,
                    escpos_base64: job?.escpos_base64 ?? null,
                    expired_jobs: backend.expiredJobs,
                }),
            };
        }
        return { ok: true, json: async () => ({ success: true }) };
    };
    return { calls, jobs, expired: backend, fetchFn };
}

function makeWorker(opts: {
    backend?: ReturnType<typeof makeBackend>;
    printerName?: string;
    printOk?: boolean;
    printError?: string;
    ledgerPath?: string;
}) {
    const backend = opts.backend ?? makeBackend();
    const events: { type: string; detail: string }[] = [];
    const printed: Buffer[] = [];
    const worker = new PrintWorker({
        baseUrl: "http://127.0.0.1:8000",
        serviceKey: "svc-key",
        printerName: opts.printerName ?? "GT710",
        ledgerPath: opts.ledgerPath,
        fetchFn: backend.fetchFn as unknown as typeof fetch,
        printFn: async (_printer: string, data: Buffer) => {
            printed.push(data);
            return opts.printOk === false
                ? { ok: false, error: opts.printError ?? "spooler fora do ar" }
                : { ok: true };
        },
        onEvent: (e: { type: string; detail: string }) => events.push(e),
    });
    return { worker, backend, events, printed };
}

function jobOf(orderId: string, payload = "ESC/POS do pedido") {
    return {
        id: `print-${orderId}-1`,
        order_id: orderId,
        escpos_base64: Buffer.from(payload, "utf-8").toString("base64"),
    };
}

test("fila vazia: reporta ONLINE e não imprime nada", async () => {
    const { worker, backend, printed } = makeWorker({});

    const result = await worker.tick();

    assert.equal(result.printed, false);
    assert.equal(printed.length, 0);
    assert.equal(worker.status().state, "ONLINE");
    assert.equal(worker.status().printed, 0);
    const statusCall = backend.calls.find((c) => c.url.endsWith("/printer/agent/status"));
    assert.ok(statusCall, "deveria publicar o estado da impressora");
    assert.equal((statusCall!.body as { status: string }).status, "ONLINE");
});

test("sem impressora escolhida: NOT_CONFIGURED e não consome a fila", async () => {
    const backend = makeBackend([jobOf("000001")]);
    const { worker } = makeWorker({ backend, printerName: "" });

    const result = await worker.tick();

    assert.equal(result.printed, false);
    assert.equal(worker.status().state, "NOT_CONFIGURED");
    // Não pode pegar job de uma fila que não tem como imprimir
    assert.equal(backend.calls.some((c) => c.url.includes("/printer/agent/next")), false);
    assert.equal(backend.jobs.length, 1);
});

test("job na fila: imprime os bytes e reporta sucesso", async () => {
    const backend = makeBackend([jobOf("000123", "CUPOM-REAL")]);
    const { worker, printed, events } = makeWorker({ backend });

    const result = await worker.tick();

    assert.equal(result.printed, true);
    assert.equal(result.orderId, "000123");
    assert.equal(printed.length, 1);
    // Os bytes chegaram ao transporte decodificados (não em base64)
    assert.equal(printed[0].toString("utf-8"), "CUPOM-REAL");
    assert.equal(worker.status().printed, 1);
    assert.equal(worker.status().state, "ONLINE");
    assert.equal(events[0].type, "printed");

    const resultCall = backend.calls.find((c) => c.url.includes("/result"));
    assert.ok(resultCall);
    const body = resultCall!.body as { success: boolean; printer_name: string };
    assert.equal(body.success, true);
    assert.equal(body.printer_name, "GT710");
});

test("falha da impressora: reporta o motivo e conta como falha", async () => {
    const backend = makeBackend([jobOf("000124")]);
    const { worker, events } = makeWorker({
        backend,
        printOk: false,
        printError: "OpenPrinter falhou (impressora não encontrada: GT710)",
    });

    await worker.tick();

    const status = worker.status();
    assert.equal(status.failed, 1);
    assert.equal(status.printed, 0);
    assert.equal(status.state, "ERROR");
    assert.match(status.lastError, /OpenPrinter/);
    assert.equal(events[0].type, "failed");
    assert.match(events[0].detail, /000124/);

    const body = backend.calls.find((c) => c.url.includes("/result"))!.body as {
        success: boolean;
        error: string;
    };
    assert.equal(body.success, false);
    assert.match(body.error, /OpenPrinter/);
});

test("backend fora do ar não é reportado como impressora offline", async () => {
    const worker = new PrintWorker({
        baseUrl: "http://127.0.0.1:8000",
        serviceKey: "svc-key",
        printerName: "GT710",
        fetchFn: (async () => {
            throw new Error("ECONNREFUSED");
        }) as unknown as typeof fetch,
        printFn: async () => ({ ok: true }),
    });

    const result = await worker.tick();

    assert.equal(result.printed, false);
    assert.equal(worker.status().state, "ERROR");
    // Nenhum POST de status inventando que a impressora está ONLINE
    assert.match(worker.status().lastError, /fila de impressão/);
});

test("status só é publicado quando muda (sem POST a cada poll parado)", async () => {
    const backend = makeBackend();
    const { worker } = makeWorker({ backend });

    await worker.tick();
    await worker.tick();
    await worker.tick();

    const statusCalls = backend.calls.filter((c) => c.url.endsWith("/printer/agent/status"));
    assert.equal(statusCalls.length, 1, "estado repetido não deveria ser reenviado");
});

test("troca de impressora em runtime força novo relato de estado", async () => {
    const backend = makeBackend();
    const { worker } = makeWorker({ backend });

    await worker.tick();
    worker.setPrinterName("Outra-Termica");
    await worker.tick();

    const statusCalls = backend.calls.filter((c) => c.url.endsWith("/printer/agent/status"));
    assert.equal(statusCalls.length, 2);
    assert.equal(worker.status().printerName, "Outra-Termica");
});

function tmpLedger(): string {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gasflow-ledger-"));
    return path.join(dir, "printed-jobs.json");
}

test("job devolvido à fila NÃO imprime duas vezes (ledger em disco)", async () => {
    // Mesmo job id duas vezes = o backend devolveu o job à fila porque o POST
    // do resultado se perdeu. O cupom não pode sair de novo.
    const ledgerPath = tmpLedger();
    const backend = makeBackend([jobOf("000900"), jobOf("000900")]);
    const { worker, printed, events } = makeWorker({ backend, ledgerPath });

    await worker.tick(); // imprime de verdade
    await worker.tick(); // mesmo job de volta: re-reporta, não reimprime

    assert.equal(printed.length, 1, "o spooler não pode receber o cupom duas vezes");
    assert.equal(worker.status().printed, 1);
    assert.equal(worker.status().replayed, 1);
    assert.deepEqual(
        events.map((e) => e.type),
        ["printed", "replayed"]
    );

    // O segundo resultado também é reportado como sucesso — senão o job ficaria
    // pendente para sempre no backend.
    const resultCalls = backend.calls.filter((c) => c.url.includes("/result"));
    assert.equal(resultCalls.length, 2);
    assert.equal((resultCalls[1].body as { success: boolean }).success, true);
});

test("o ledger sobrevive ao restart do app", async () => {
    const ledgerPath = tmpLedger();
    const first = makeWorker({ backend: makeBackend([jobOf("000901")]), ledgerPath });
    await first.worker.tick();
    assert.equal(first.printed.length, 1);

    // App fechou e reabriu com o job ainda na fila (relato perdido de novo):
    // o novo worker lê o arquivo e não reimprime.
    const restarted = makeWorker({ backend: makeBackend([jobOf("000901")]), ledgerPath });
    await restarted.worker.tick();

    assert.equal(restarted.printed.length, 0);
    assert.equal(restarted.worker.status().replayed, 1);
});

test("relato de status perdido é reenviado no próximo ciclo", async () => {
    // 1º POST de status falha (backend reiniciando no meio do orquestrador).
    // Antes o worker cacheava o estado ANTES de enviar e nunca mais reenviava:
    // a tela ficava presa em "Não configurada" com a impressora funcionando.
    let statusAttempts = 0;
    const statusCalls: string[] = [];
    const fetchFn = (async (url: string, init: { method?: string } = {}) => {
        if (!String(url).endsWith("/printer/agent/status")) {
            return { ok: true, json: async () => ({ job: null, escpos_base64: null }) };
        }
        statusAttempts += 1;
        statusCalls.push(init.method ?? "GET");
        if (statusAttempts === 1) throw new Error("ECONNRESET");
        return { ok: true, json: async () => ({ success: true }) };
    }) as unknown as typeof fetch;

    const worker = new PrintWorker({
        baseUrl: "http://127.0.0.1:8000",
        serviceKey: "svc-key",
        printerName: "GT710",
        fetchFn,
        printFn: async () => ({ ok: true }),
    });

    await worker.tick();
    await worker.tick();

    assert.equal(statusCalls.length, 2, "o estado não confirmado deve ser reenviado");
});

test("401 na chave de serviço tem diagnóstico próprio (não é 'backend fora')", async () => {
    const worker = new PrintWorker({
        baseUrl: "http://127.0.0.1:8000",
        serviceKey: "chave-errada",
        printerName: "GT710",
        fetchFn: (async () => ({ ok: false, status: 401, json: async () => ({}) })) as unknown as typeof fetch,
        printFn: async () => ({ ok: true }),
    });

    await worker.tick();

    assert.equal(worker.status().state, "ERROR");
    assert.match(worker.status().lastError, /chave de serviço rejeitada/);
    assert.doesNotMatch(worker.status().lastError, /fila de impressão/);
});

test("5xx no backend é reportado como erro de fila (não como térmica fora)", async () => {
    const worker = new PrintWorker({
        baseUrl: "http://127.0.0.1:8000",
        serviceKey: "svc-key",
        printerName: "GT710",
        fetchFn: (async () => ({ ok: false, status: 503, json: async () => ({}) })) as unknown as typeof fetch,
        printFn: async () => ({ ok: true }),
    });

    await worker.tick();

    assert.match(worker.status().lastError, /fila de impressão/);
    assert.match(worker.status().lastError, /503/);
});

test("cupom vencido avisa o operador UMA vez (e de novo se aparecer mais)", async () => {
    // O vencimento nasce no backend (cupom de dia anterior) e chega no poll.
    // Sem este aviso o pedido fica sem cupom em silêncio: não sai papel, logo
    // não existe "erro" para a tela mostrar.
    const backend = makeBackend([], 2);
    const { worker, events } = makeWorker({ backend });

    await worker.tick();
    await worker.tick(); // mesmo total: não repete o aviso a cada 3s
    assert.equal(events.filter((e) => e.type === "expired").length, 1);
    assert.match(events[0].detail, /2 cupom\(ns\) de dia anterior/);

    // Venceu mais um enquanto o app estava aberto
    backend.expired.expiredJobs = 3;
    await worker.tick();
    const avisos = events.filter((e) => e.type === "expired");
    assert.equal(avisos.length, 2);
    assert.match(avisos[1].detail, /3 cupom\(ns\) de dia anterior/);
});

test("sem cupom vencido não há aviso nenhum", async () => {
    const backend = makeBackend([], 0);
    const { worker, events } = makeWorker({ backend });

    await worker.tick();
    await worker.tick();

    assert.equal(events.filter((e) => e.type === "expired").length, 0);
});

test("isHealthy acompanha o worker (base para o orquestrador)", async () => {
    const { worker } = makeWorker({});

    assert.equal(worker.isHealthy(), false, "parado não é saudável");

    worker.start();
    assert.equal(worker.isHealthy(), true, "recém-iniciado conta como subindo");
    worker.stop();

    assert.equal(worker.isHealthy(), false);
});

test("start/stop são idempotentes", () => {
    const { worker } = makeWorker({});

    worker.start();
    worker.start();
    assert.equal(worker.running, true);
    worker.stop();
    worker.stop();
    assert.equal(worker.running, false);
});
