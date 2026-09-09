import { runDueIntegrations } from "./src/runner";
import { GasFlowClient } from "./src/gasflow-client";
import type { IntegrationConfig } from "./src/types";

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

async function main() {
  const sentPaths: string[] = [];
  const mockApi = new GasFlowClient({ baseUrl: "http://mock.invalid", token: "x" });
  (mockApi as unknown as { request: (p: string, i?: RequestInit) => Promise<unknown> }).request = async (
    path: string
  ) => {
    sentPaths.push(path);
    if (path.startsWith("/api/v1/integrations?")) {
      return {
        integrations: [
          { ...integrationOf("http://127.0.0.1:1"), id: "due-1", last_sync_at: null },
          {
            ...integrationOf("http://127.0.0.1:2"),
            id: "not-due",
            last_sync_at: new Date(Date.now() - 30_000).toISOString(),
          },
          { ...integrationOf("http://127.0.0.1:3"), id: "due-ok" },
        ],
      };
    }
    if (path.includes("/sync-run")) return { status: "success" };
    return {};
  };

  const outcomes = await runDueIntegrations(mockApi);
  console.log(JSON.stringify(outcomes, null, 1));
  console.log("paths:", sentPaths);
}
main();
