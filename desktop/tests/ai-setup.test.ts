/**
 * Testes do ai-setup (Item 3) — dist/main/ai-setup.js com HTTP/eletrônicos
 * stubados. Cobre o contrato do prompt 3.1 no cenário B (sem fallback):
 *   1. Ollama ausente + dono recusa → estado "skipped", sem instalar
 *   2. Modelo ausente → POST /api/pull com progresso → "ready"
 *   3. run() nunca lança nem bloqueia (erros viram estado)
 *   4. Sem diálogo/consentimento → NUNCA instala
 *   5. Falhas de rede → 3 tentativas com backoff antes de degradar
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { createRequire } from "node:module";

const req = createRequire(__filename);
const aiSetupPath = path.resolve(__dirname, "../dist/main/ai-setup.js");
const { AiSetupRunner, mergeAiState, findOllamaBinary, candidateOllamaPaths } = req(aiSetupPath);

/** http stub: cada handler responde a um URL com uma sequência de corpos NDJSON. */
function fakeHttp(routes) {
    const calls = [];
    const respond = (url) => {
        calls.push(url);
        for (const [prefix, handler] of Object.entries(routes)) {
            if (url.includes(prefix)) return handler;
        }
        return () => ({ statusCode: 404, headers: {} });
    };
    return {
        calls,
        request: (url, _opts, cb) => {
            const res = respond(String(url));
            process.nextTick(() => cb(res())); // res() = handler devolve a resposta
            return {
                setTimeout() {},
                destroy() {},
                on(_evt, _fn) {},
                write() {},
                end() {},
            };
        },
    };
}

function makeRunner(overrides = {}) {
    const events = [];
    const saved = [];
    const deps = {
        baseUrl: "http://127.0.0.1:11434",
        modelName: "qwen3:0.6b",
        existsFile: () => false,
        notifyOwner: async () => false,
        sleep: async () => undefined, // backoff instantâneo nos testes
        fetchTags: async () => ({ ok: false, models: [] }),
        httpModule: fakeHttp({}),
        onProgress: (p) => events.push(["progress", p]),
        onStatusChanged: (s) => events.push(["status", s.state]),
        saveState: (s) => saved.push(s),
        ...overrides,
    };
    const runner = new AiSetupRunner(deps);
    return { runner, events, saved };
}

test("detecta Ollama ausente e marca skipped quando o dono recusa (sem instalar)", async () => {
    let installCalls = 0;
    const { runner, events, saved } = makeRunner({
        notifyOwner: async () => false,
        installOllama: async () => {
            installCalls++;
            return true;
        },
    });
    const status = await runner.run();
    assert.equal(status.state, "skipped");
    assert.equal(status.installed, false);
    assert.equal(installCalls, 0, "recusa → NUNCA instala");
    assert.ok(saved.length > 0, "estado persistido em settings.json");
    assert.equal(events.at(-1)[1], "skipped");
});

test("modelo ausente → pull com progresso e estado ready", async () => {
    let pullRequests = 0;
    const httpMod = fakeHttp({
        "/api/pull": () => {
            pullRequests++;
            return {
                statusCode: 200,
                resume() {},
                setEncoding() {},
                headers: {},
                on(evt, fn) {
                    if (evt === "data") {
                        process.nextTick(() =>
                            fn(
                                JSON.stringify({ status: "pulling", total: 800, completed: 400 }) +
                                    "\n" +
                                    JSON.stringify({ status: "success" }),
                            ),
                        );
                    }
                    if (evt === "end") process.nextTick(fn);
                },
            };
        },
    });
    let tagCalls = 0;
    const { runner, events } = makeRunner({
        existsFile: () => true, // binário presente
        httpModule: httpMod,
        // 1º check: instalado, modelo ausente; 2º (pós-pull): ready
        fetchTags: async () => ({ ok: true, models: tagCalls++ === 0 ? ["llama3.2"] : ["qwen3:0.6b"] }),
    });
    const status = await runner.run();
    assert.equal(pullRequests, 1, "exatamente um POST /api/pull");
    assert.equal(status.state, "ready");
    assert.equal(status.modelReady, true);
    const percents = events.filter(([k]) => k === "progress").map(([, p]) => p.percent);
    assert.ok(percents.includes(50), `progresso intermediário emitido (${percents.join(",")})`);
    assert.ok(percents.includes(100), "progresso final 100%");
});

test("run() nunca lança — falha de rede vira estado unavailable e não bloqueia", async () => {
    const { runner } = makeRunner({
        existsFile: () => true,
        fetchTags: async () => {
            throw new Error("ECONNREFUSED");
        },
    });
    const status = await runner.run();
    assert.equal(status.state, "unavailable");
});

test("sem diálogo (notifyOwner ausente) o instalador nunca é baixado", async () => {
    let downloads = 0;
    const { runner } = makeRunner({
        notifyOwner: null, // sem diálogo configurado
        installOllama: async () => {
            downloads++;
            return true;
        },
        fetchTags: async () => ({ ok: false, models: [] }),
    });
    const status = await runner.run();
    assert.equal(downloads, 0, "sem consentimento explícito → sem download");
    assert.equal(status.state, "skipped");
});

test("falhas de pull repetem 3x com backoff antes de degradar", async () => {
    let attempts = 0;
    const httpMod = fakeHttp({
        "/api/pull": () => {
            attempts++;
            return { statusCode: 500, headers: {} }; // sem resume() — cobre o caminho defensivo
        },
    });
    const sleeps = [];
    const { runner } = makeRunner({
        existsFile: () => true,
        httpModule: httpMod,
        fetchTags: async () => ({ ok: true, models: [] }),
        sleep: async (ms) => sleeps.push(ms),
    });
    const status = await runner.run();
    assert.equal(attempts, 3, `3 tentativas (feitas: ${attempts})`);
    assert.deepEqual(sleeps, [1000, 2000], "backoff exponencial 1s → 2s");
    assert.equal(status.state, "unavailable");
});

test("findOllamaBinary acha binário nos caminhos usuais e mergeAiState preserva chaves", () => {
    const existing = ["C:\\Program Files\\Ollama\\ollama.exe"];
    assert.equal(findOllamaBinary(null, (p) => existing.includes(p), candidateOllamaPaths()), existing[0]);
    assert.equal(findOllamaBinary(null, () => false, candidateOllamaPaths()), null);
    const merged = mergeAiState({ waPort: 3101, ai: { installed: true } }, { state: "ready" });
    assert.equal(merged.waPort, 3101);
    assert.equal(merged.ai.installed, true);
    assert.equal(merged.ai.state, "ready");
});
