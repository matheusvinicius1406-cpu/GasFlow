/**
 * Testes do modo IPC do agente (createAgentIpc) — sem subprocesso: PassThrough
 * como stdin e coletor em memória como saída. Casos de rede usam apenas o
 * comportamento determinístico de erro (sem cliente configurado / API inacessível).
 */

import assert from "node:assert/strict";
import { PassThrough } from "node:stream";
import test from "node:test";
import { createAgentIpc, type IpcOutLine } from "../src/ipc";

interface Harness {
  input: PassThrough;
  lines: IpcOutLine[];
}

function startAgentIpc(): Harness {
  const input = new PassThrough();
  const lines: IpcOutLine[] = [];
  createAgentIpc(input, (line) => lines.push(line));
  return { input, lines };
}

/** Envia um comando e espera a resposta correspondente (por id) com timeout. */
async function request(h: Harness, id: string, cmd: string, params: Record<string, unknown> = {}): Promise<IpcOutLine> {
  const before = h.lines.length;
  h.input.write(`${JSON.stringify({ id, cmd, params })}\n`);
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const found = h.lines.slice(before).find((l) => "id" in l && l.id === id);
    if (found) return found;
    await new Promise((r) => setTimeout(r, 20));
  }
  throw new Error(`timeout aguardando resposta id=${id}`);
}

function waitFor(h: Harness, pred: (l: IpcOutLine) => boolean): Promise<IpcOutLine> {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 5000;
    const check = (): void => {
      const found = h.lines.find(pred);
      if (found) return resolve(found);
      if (Date.now() > deadline) return reject(new Error("timeout aguardando evento"));
      setTimeout(check, 20);
    };
    check();
  });
}

test("ipc: emite ready ao iniciar", async () => {
  const h = startAgentIpc();
  await waitFor(h, (l) => "event" in l && l.event === "ready");
});

test("ipc: ping responde pong sem configuração", async () => {
  const h = startAgentIpc();
  const res = await request(h, "1", "ping");
  assert.equal(res.ok, true);
  assert.deepEqual((res as { data: { pong: boolean } }).data, { pong: true, pid: process.pid, mode: "ipc" });
});

test("ipc: linha inválida gera erro parseável", async () => {
  const h = startAgentIpc();
  h.input.write("isto não é json\n");
  const res = await waitFor(h, (l) => "ok" in l && l.ok === false);
  assert.match((res as { error: string }).error, /inválida/i);
});

test("ipc: comando desconhecido retorna erro", async () => {
  const h = startAgentIpc();
  const res = await request(h, "9", "flyingSpaghetti");
  assert.equal(res.ok, false);
  assert.match((res as { error: string }).error, /desconhecido/i);
});

test("ipc: listIntegrations sem configure falha com mensagem clara", async () => {
  const h = startAgentIpc();
  const res = await request(h, "2", "listIntegrations");
  assert.equal(res.ok, false);
  assert.match((res as { error: string }).error, /configure/i);
});

test("ipc: configure sem token falha", async () => {
  const h = startAgentIpc();
  const res = await request(h, "3", "configure", { apiUrl: "http://localhost:8000" });
  assert.equal(res.ok, false);
  assert.match((res as { error: string }).error, /token/i);
});

test("ipc: sync sem configure falha sem travar", async () => {
  const h = startAgentIpc();
  const res = await request(h, "4", "sync");
  assert.equal(res.ok, false);
  assert.match((res as { error: string }).error, /configure/i);
});

test("ipc: configure com token falso fica pronto e sync reporta erro de rede", async () => {
  const h = startAgentIpc();
  const cfg = await request(h, "5", "configure", { apiUrl: "http://127.0.0.1:9", token: "x" });
  assert.equal(cfg.ok, true);

  const res = await request(h, "6", "sync");
  assert.equal(res.ok, false);
  assert.match((res as { error: string }).error, /Falha na sincronização/i);
});

test("ipc: sync de integração específica em API inacessível falha com erro de rede", async () => {
  const h = startAgentIpc();
  await request(h, "7", "configure", { apiUrl: "http://127.0.0.1:9", token: "x" });

  const res = await request(h, "8", "sync", { integrationId: "abc" });
  assert.equal(res.ok, false);
  assert.match((res as { error: string }).error, /Falha na sincronização/i);
});
