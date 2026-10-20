/**
 * Testes do AgentBridge (dist/main/agent-bridge.js) — protocolo JSON-lines
 * sobre stdio do subprocesso do agente, usando um child falso (sem spawn).
 * O bridge foi desenhado para isso: attach(child) é público justamente para
 * permitir teste sem Electron nem processo real.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { createRequire } from "node:module";

const req = createRequire(__filename);
const { AgentBridge } = req("../dist/main/agent-bridge.js") as {
  AgentBridge: new (opts: Record<string, unknown>) => AgentBridgeLike;
};

interface AgentBridgeLike extends EventEmitter {
  child: FakeChild | null;
  stopping: boolean;
  running: boolean;
  status(): { running: boolean; pid?: number; lastError?: string };
  attach(child: FakeChild): void;
  request(cmd: string, params?: unknown, timeoutMs?: number): Promise<{ ok: boolean; data?: unknown; error?: string }>;
  onStdout(chunk: string): void;
  listIntegrations(includeInactive?: boolean): Promise<unknown>;
}

interface FakeChild extends EventEmitter {
  pid: number;
  exitCode: number | null;
  written: string[];
  stdin: { write: (s: string) => void };
  stdout: EventEmitter & { setEncoding: (enc: string) => void };
  stderr: EventEmitter & { setEncoding: (enc: string) => void };
  kill: (signal?: string) => void;
  killed: boolean;
}

function makeChild(): FakeChild {
  const child = new EventEmitter() as FakeChild;
  child.pid = 4321;
  child.exitCode = null;
  child.written = [];
  child.killed = false;
  child.stdout = new EventEmitter() as FakeChild["stdout"];
  child.stdout.setEncoding = () => undefined;
  child.stderr = new EventEmitter() as FakeChild["stderr"];
  child.stderr.setEncoding = () => undefined;
  child.stdin = { write: (s: string) => { child.written.push(s); } };
  child.kill = () => { child.killed = true; };
  return child;
}

/** Bridge ligado a um child falso (o que start() faria, sem spawn real). */
function makeBridge(overrides: Record<string, unknown> = {}) {
  const bridge = new AgentBridge({
    command: "node",
    args: ["agent/dist/index.js", "--ipc"],
    getCredentials: () => ({ apiUrl: "http://127.0.0.1:8000", token: "tok-123" }),
    ...overrides,
  });
  const child = makeChild();
  bridge.attach(child);
  bridge.child = child;
  return { bridge, child };
}

function lastRequest(child: FakeChild): { id: string; cmd: string; params: unknown } {
  assert.ok(child.written.length > 0, "o bridge deve ter escrito algo no stdin");
  return JSON.parse(child.written[child.written.length - 1].replace(/\n$/, ""));
}

// ── request/response por id ────────────────────────────────────────────

test("request escreve JSON-lines no stdin e correlaciona a resposta pelo id", async () => {
  const { bridge, child } = makeBridge();
  const pending = bridge.request("listIntegrations", { includeInactive: false });

  const sent = lastRequest(child);
  assert.equal(sent.cmd, "listIntegrations");
  assert.deepEqual(sent.params, { includeInactive: false });
  assert.match(sent.id, /^\d+$/);
  assert.ok(child.written[child.written.length - 1].endsWith("\n"), "linha termina em \\n");

  child.stdout.emit("data", JSON.stringify({ id: sent.id, ok: true, data: [{ id: "sf" }] }) + "\n");
  assert.deepEqual(await pending, { ok: true, data: [{ id: "sf" }] });
});

test("resposta ok:false vira { ok:false, error } (não lança)", async () => {
  const { bridge, child } = makeBridge();
  const pending = bridge.request("sync", {});
  const sent = lastRequest(child);
  child.stdout.emit("data", JSON.stringify({ id: sent.id, ok: false, error: "sem token" }) + "\n");
  assert.deepEqual(await pending, { ok: false, error: "sem token" });
});

test("ids avançam por chamada (correlação sem colisão)", async () => {
  const { bridge, child } = makeBridge();
  const first = bridge.request("a");
  const idA = lastRequest(child).id;
  const second = bridge.request("b");
  const idB = lastRequest(child).id;
  assert.notEqual(idA, idB);

  child.stdout.emit("data", JSON.stringify({ id: idB, ok: true, data: "b-ok" }) + "\n");
  child.stdout.emit("data", JSON.stringify({ id: idA, ok: true, data: "a-ok" }) + "\n");
  assert.deepEqual(await second, { ok: true, data: "b-ok" });
  assert.deepEqual(await first, { ok: true, data: "a-ok" });
});

test("request fora de running rejeita com mensagem acionável", async () => {
  const bridge = new AgentBridge({ command: "node", args: [], getCredentials: () => ({ apiUrl: "", token: "" }) });
  await assert.rejects(() => bridge.request("listIntegrations"), /não está rodando/);
});

test("request com timeout rejeita e limpa o pending", async () => {
  const { bridge } = makeBridge();
  await assert.rejects(() => bridge.request("sync", {}, 20), /timeout .* no comando "sync"/);
});

// ── buffering do stdout (JSON-lines parciais) ──────────────────────────

test("chunk parcial fica no buffer até chegar o \\n", async () => {
  const { bridge, child } = makeBridge();
  const pending = bridge.request("x");
  const id = lastRequest(child).id;

  child.stdout.emit("data", `{"id":"${id}",`);
  assert.equal(child.written.length, 1, "sem \\n ainda não processa");

  child.stdout.emit("data", `"ok":true,"data":42}\n`);
  assert.deepEqual(await pending, { ok: true, data: 42 });
});

test("várias linhas num único chunk são processadas em ordem", async () => {
  const { bridge } = makeBridge();
  const logs: string[] = [];
  bridge.on("log", (l: { message: string }) => logs.push(l.message));

  bridge.onStdout(
    JSON.stringify({ event: "log", level: "info", scope: "agent", message: "um" }) + "\n" +
    JSON.stringify({ event: "log", level: "warn", scope: "agent", message: "dois" }) + "\n",
  );
  assert.deepEqual(logs, ["um", "dois"]);
});

// ── eventos do agente ──────────────────────────────────────────────────

test("event ready emite agent-ready (é o que destrava o start())", () => {
  const { bridge } = makeBridge();
  let ready = 0;
  bridge.on("agent-ready", () => { ready += 1; });
  bridge.onStdout(JSON.stringify({ event: "ready" }) + "\n");
  assert.equal(ready, 1);
});

test("event log repassa level e message (scope é normalizado para 'agent')", () => {
  const { bridge } = makeBridge();
  const seen: Array<Record<string, unknown>> = [];
  bridge.on("log", (l: Record<string, unknown>) => seen.push(l));
  bridge.onStdout(JSON.stringify({ event: "log", level: "warn", scope: "sync", message: "lento" }) + "\n");
  // Comportamento atual do bridge: o scope do agente não é propagado — o log
  // é emitido sob o scope "agent" (é o que index.ts imprime).
  assert.deepEqual(seen, [{ level: "warn", scope: "agent", message: "lento" }]);
});

test("event outcome repassa o payload inteiro para a UI notificar", () => {
  const { bridge } = makeBridge();
  const outcomes: unknown[] = [];
  bridge.on("outcome", (o: unknown) => outcomes.push(o));
  const outcome = { integrationName: "tiny-bahia", ok: true, message: "3 contatos" };
  bridge.onStdout(JSON.stringify({ event: "outcome", outcome }) + "\n");
  assert.deepEqual(outcomes, [outcome]);
});

// ── resiliência a stdout fora do protocolo ─────────────────────────────

test("linha não-JSON (warning de lib) vira log e não derruba o bridge", () => {
  const { bridge } = makeBridge();
  const logs: Array<{ level: string; message: string }> = [];
  bridge.on("log", (l: { level: string; message: string }) => logs.push(l));
  bridge.onStdout("DeprecationWarning: something\n");
  assert.equal(logs.length, 1);
  assert.equal(logs[0].level, "info");
  assert.equal(logs[0].message, "DeprecationWarning: something");
  assert.equal(bridge.running, true, "bridge segue vivo");
});

test("linha em branco é ignorada", () => {
  const { bridge } = makeBridge();
  let logs = 0;
  bridge.on("log", () => { logs += 1; });
  bridge.onStdout("\n\n  \n");
  assert.equal(logs, 0);
});

test("stderr vira um evento log por linha não vazia", () => {
  const { bridge, child } = makeBridge();
  const logs: string[] = [];
  bridge.on("log", (l: { level: string; message: string }) => {
    assert.equal(l.level, "error");
    logs.push(l.message);
  });
  child.stderr.emit("data", "erro um\n\nerro dois\n");
  assert.deepEqual(logs, ["erro um", "erro dois"]);
});

// ── ciclo de vida: error/exit ──────────────────────────────────────────

test("error do spawn registra lastError e emite status", () => {
  const { bridge, child } = makeBridge();
  const statuses: Array<{ running: boolean }> = [];
  bridge.on("status", (s: { running: boolean }) => statuses.push(s));
  child.emit("error", new Error("ENOENT"));
  assert.equal(bridge.status().lastError, "ENOENT");
  assert.equal(statuses[statuses.length - 1].running, false);
});

test("error do spawn limpa o child e rejeita pending (não fica running fantasma)", async () => {
  const { bridge, child } = makeBridge();
  const pending = bridge.request("sync", {}, 60_000);

  child.emit("error", new Error("ENOENT"));

  assert.equal(bridge.running, false, "spawn que falhou não pode continuar 'running'");
  assert.equal(bridge.child, null);
  assert.deepEqual(await pending, { ok: false, error: "falha ao iniciar agente: ENOENT" });
});

test("exit inesperado rejeita pending com { ok:false } e zera o running", async () => {
  const { bridge, child } = makeBridge();
  const pending = bridge.request("sync", {}, 60_000);
  const errors: string[] = [];
  bridge.on("log", (l: { level: string; message: string }) => errors.push(`${l.level}:${l.message}`));

  child.exitCode = 1;
  child.emit("exit", 1, null);

  assert.deepEqual(await pending, { ok: false, error: "agente não está mais rodando" });
  assert.equal(bridge.running, false);
  assert.equal(bridge.child, null);
  assert.ok(errors.some((e) => e.startsWith("error:") && e.includes("inesperadamente")));
});

test("exit após stop() é tratado como info (não é falha)", () => {
  const { bridge, child } = makeBridge();
  const logs: string[] = [];
  bridge.on("log", (l: { level: string; message: string }) => logs.push(`${l.level}:${l.message}`));
  bridge.stopping = true;
  child.exitCode = 0;
  child.emit("exit", 0, null);
  assert.ok(logs.some((l) => l.startsWith("info:") && l.includes("agente encerrado")));
  assert.ok(!logs.some((l) => l.startsWith("error:")));
});

test("status() espelha o child anexado", () => {
  const { bridge, child } = makeBridge();
  assert.deepEqual(bridge.status(), { running: true, pid: 4321, lastError: undefined });
  child.exitCode = 0;
  bridge.child = null;
  assert.equal(bridge.status().running, false);
});
