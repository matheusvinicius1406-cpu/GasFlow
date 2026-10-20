/**
 * Regressão do spawn que falha (ENOENT/EACCES) nos bridges de subprocesso do
 * main: antes, o `child` continuava non-null com `exitCode === null`, então
 * `running` ficava true e `start()` esperava o health check inteiro (90s no
 * backend, 20s no WhatsApp) antes de mostrar o erro real.
 *
 * O spawn é trocado por um child falso que emite `error` no próximo tick; o
 * fetch do health check falha de propósito.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import Module from "node:module";
import { createRequire } from "node:module";

interface FakeChild extends EventEmitter {
  pid: number;
  exitCode: number | null;
  stdout: EventEmitter & { setEncoding: (enc: string) => void };
  stderr: EventEmitter & { setEncoding: (enc: string) => void };
  kill: () => void;
}

function makeChild(): FakeChild {
  const child = new EventEmitter() as FakeChild;
  child.pid = 999;
  child.exitCode = null;
  child.stdout = new EventEmitter() as FakeChild["stdout"];
  child.stdout.setEncoding = () => undefined;
  child.stderr = new EventEmitter() as FakeChild["stderr"];
  child.stderr.setEncoding = () => undefined;
  child.kill = () => undefined;
  return child;
}

const origRequire = Module.prototype.require;
Module.prototype.require = function (this: unknown, id: string) {
  if (id === "node:child_process") {
    return {
      spawn: () => {
        const child = makeChild();
        // O handler de `error` só é anexado depois que spawn() retorna.
        process.nextTick(() => child.emit("error", new Error("ENOENT")));
        return child;
      },
    };
  }
  return origRequire.apply(this, arguments as unknown as Parameters<typeof origRequire>);
};

const req = createRequire(__filename);
const { BackendBridge } = req("../dist/main/backend-bridge.js") as {
  BackendBridge: new (opts: Record<string, unknown>, onLog: (level: string, scope: string, message: string) => void) => {
    running: boolean;
    child: FakeChild | null;
    start: () => Promise<void>;
  };
};
const { WhatsAppBridge } = req("../dist/main/wa-bridge.js") as {
  WhatsAppBridge: new (opts: Record<string, unknown>) => {
    running: boolean;
    child: FakeChild | null;
    start: (waitMs?: number) => Promise<unknown>;
  };
};

const failingFetch = async (): Promise<Response> => {
  throw new Error("offline");
};

test("BackendBridge: spawn que falha zera o child e falha antes do health check inteiro", async () => {
  const bridge = new BackendBridge(
    {
      command: "python-que-nao-existe",
      args: [],
      cwd: ".",
      env: {},
      healthUrl: "http://127.0.0.1:9/health",
      waitMs: 5_000,
      fetchFn: failingFetch,
    },
    () => undefined,
  );

  const t0 = Date.now();
  await assert.rejects(() => bridge.start(), /saiu durante a inicialização/);
  assert.equal(bridge.running, false, "não pode ficar running depois de ENOENT");
  assert.equal(bridge.child, null);
  assert.ok(Date.now() - t0 < 4_000, "deve falhar no primeiro ciclo, sem esperar o deadline");
});

test("WhatsAppBridge: spawn que falha zera o child e falha antes do timeout", async () => {
  const bridge = new WhatsAppBridge({
    command: "node-que-nao-existe",
    args: [],
    cwd: ".",
    env: {},
    baseUrl: "http://127.0.0.1:9",
    waitMs: 5_000,
    fetchFn: failingFetch,
  });

  const t0 = Date.now();
  await assert.rejects(() => bridge.start(5_000), /saiu durante a inicialização/);
  assert.equal(bridge.running, false, "não pode ficar running depois de ENOENT");
  assert.equal(bridge.child, null);
  assert.ok(Date.now() - t0 < 4_000, "deve falhar no primeiro ciclo, sem esperar o deadline");
});
