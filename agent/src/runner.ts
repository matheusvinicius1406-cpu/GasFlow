/**
 * Runner — executa a sincronização de uma integração:
 *   página de pedidos → detector → normalizer → POST sync-run.
 */

import { detect } from "./detector";
import { discoverOrdersPage, fetchHtml } from "./fetcher";
import { tableToOrders } from "./normalizer";
import type { GasFlowClient } from "./gasflow-client";
import type { AgentError, IntegrationConfig, NormalizedOrder } from "./types";

export interface SyncOutcome {
  integrationId: string;
  integrationName: string;
  ok: boolean;
  totalFound: number;
  imported: number;
  errors: AgentError[];
  message: string;
}

function authOf(integration: IntegrationConfig) {
  return { type: integration.auth_type, config: integration.auth_config };
}

/** Sincroniza UMA integração (completo: fetch → detect → extract → send). */
export async function syncIntegration(
  integration: IntegrationConfig,
  client: GasFlowClient
): Promise<SyncOutcome> {
  const base: SyncOutcome = {
    integrationId: integration.id,
    integrationName: integration.name,
    ok: false,
    totalFound: 0,
    imported: 0,
    errors: [],
    message: "",
  };

  // 1. página de pedidos (configurada ou descoberta entre caminhos comuns)
  let page;
  if (integration.orders_path) {
    const url = `${integration.base_url.replace(/\/+$/, "")}${
      integration.orders_path.startsWith("/") ? integration.orders_path : `/${integration.orders_path}`
    }`;
    try {
      page = await fetchHtml(url, authOf(integration));
      if (page.status !== 200) throw new Error(`HTTP ${page.status} em ${url}`);
    } catch {
      page = await discoverOrdersPage(integration.base_url, authOf(integration), integration.orders_path);
    }
  } else {
    page = await discoverOrdersPage(integration.base_url, authOf(integration), null);
  }

  // 2. detecção da tabela de pedidos
  const context = detect(page.html, integration);
  if (!context.table) {
    return { ...base, message: `Nenhuma tabela de pedidos detectada em ${page.url}` };
  }

  // 3. extração + normalização
  const { orders, errors } = tableToOrders(context.table);

  // 4. envio ao backend
  await client.sendSyncRun(integration.id, { orders, errors, trigger: "agent" });

  return {
    ...base,
    ok: errors.length === 0 || orders.length > 0,
    totalFound: orders.length + errors.length,
    imported: orders.length,
    errors,
    message: `Enviados ${orders.length} pedidos (${errors.length} erros de extração) de ${page.url}`,
  };
}

/** Roda todas as integrações due. Erros de uma não derrubam as outras. */
export async function runDueIntegrations(client: GasFlowClient): Promise<SyncOutcome[]> {
  const due = await client.dueIntegrations();
  const outcomes: SyncOutcome[] = [];
  for (const integration of due) {
    try {
      outcomes.push(await syncIntegration(integration, client));
    } catch (e) {
      outcomes.push({
        integrationId: integration.id,
        integrationName: integration.name,
        ok: false,
        totalFound: 0,
        imported: 0,
        errors: [],
        message: `Falha na sincronização: ${(e as Error).message}`,
      });
    }
  }
  return outcomes;
}

export type { NormalizedOrder };
