import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { syncIntegration, runDueIntegrations } from "../src/runner";
import { GasFlowClient } from "../src/gasflow-client";
import type { IntegrationConfig, SyncRunPayload } from "../src/types";
import { ORDERS_TABLE_HTML } from "./fixtures";

function startSite(port: number): Promise<http.Server> {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      if (req.url?.startsWith("/pedidos")) {
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        res.end(ORDERS_TABLE_HTML);
      } else {
        res.writeHead(404);
        res.end();
      }
    });
    server.listen(port, "127.0.0.1", () => resolve(server));
  });
}

function integrationOf(base: string): IntegrationConfig {
  return {
    id: "int-1",
    name: "Site Local",
    base_url: base,
    orders_path: "/pedidos",
    auth_type: "none",
    field_mapping: null,
    selectors: null,
    sync_interval_minutes: 5,
  };
}

test("syncIntegration: fluxo completo contra site local + API mock", async () => {
  const site = await startSite(0);
  const addr = site.address() as { port: number };
  const base = `http://127.0.0.1:${addr.port}`;

  let received: SyncRunPayload | null = null;
  const mockApi = new GasFlowClient({ baseUrl: "http://mock.invalid", token: "x" });
  // substitui o request por captura local (sem rede)
  (mockApi as unknown as { request: (p: string, i?: RequestInit) => Promise<unknown> }).request = async (
    path: string,
    init?: RequestInit
  ) => {
    if (path.includes("/sync-run")) {
      received = JSON.parse(String(init?.body)) as SyncRunPayload;
      return { sync_log_id: "log-1", status: "success", total_imported: received.orders.length };
    }
    return { integrations: [] };
  };

  const outcome = await syncIntegration(integrationOf(base), mockApi);
  site.close();

  assert.equal(outcome.ok, true, outcome.message);
  assert.ok(received, "sync-run deveria ter sido enviado");
  assert.equal(received!.orders.length, 3);
  assert.equal(received!.orders[0].external_id, "1001");
  assert.equal(received!.trigger, "agent");
});

test("runDueIntegrations: filtra por intervalo e isola falhas", async () => {
  // site local real para a integração "due-ok" (a de porta 1 não existe de propósito)
  const site = await startSite(0);
  const addr = site.address() as { port: number };

  const sentPaths: string[] = [];
  const mockApi = new GasFlowClient({ baseUrl: "http://mock.invalid", token: "x" });
  (mockApi as unknown as {
    request: (p: string, i?: RequestInit) => Promise<unknown>;
  }).request = async (path: string, _init?: RequestInit) => {
    sentPaths.push(path);
    if (path.startsWith("/api/v1/integrations?")) {
      return {
        integrations: [
          { ...integrationOf("http://127.0.0.1:1"), id: "due-1", last_sync_at: null },
          {
            ...integrationOf("http://127.0.0.1:2"),
            id: "not-due",
            last_sync_at: new Date(Date.now() - 30_000).toISOString(), // 30s atrás, intervalo 5min
          },
          { ...integrationOf(`http://127.0.0.1:${addr.port}`), id: "due-ok" },
        ],
      };
    }
    if (path.includes("/sync-run")) {
      return { status: "success" };
    }
    return {};
  };

  const outcomes = await runDueIntegrations(mockApi);
  site.close();

  // due-1 falha (porta 1), due-ok processa contra o site local
  assert.equal(outcomes.length, 2);
  assert.equal(outcomes[0].ok, false);
  assert.equal(outcomes[1].ok, true, outcomes[1].message);
  assert.ok(outcomes[1].imported > 0, "due-ok deveria ter importado pedidos");
  assert.ok(sentPaths.some((p) => p.includes("due-ok/sync-run")));
  assert.ok(!sentPaths.some((p) => p.includes("not-due")));
});
