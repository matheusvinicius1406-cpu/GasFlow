/**
 * Cliente HTTP do agente para o backend GasFlow.
 *
 * Pull model: o agente pergunta quais integrações estão "due" e entrega os
 * lotes via POST /integrations/{id}/sync-run. Autenticação: credenciais de
 * usuário de serviço (Basic via bearer token) — mesma confiança do serviço
 * WhatsApp.
 */

import type { IntegrationConfig, SyncRunPayload } from "./types";

export interface GasFlowClientOptions {
  baseUrl: string;
  token: string;
  timeoutMs?: number;
}

export class GasFlowClient {
  private baseUrl: string;
  private token: string;
  private timeoutMs: number;

  constructor(opts: GasFlowClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.token = opts.token;
    this.timeoutMs = opts.timeoutMs ?? 20000;
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`,
          ...(init?.headers ?? {}),
        },
        signal: controller.signal,
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = (body as { detail?: string }).detail ?? `HTTP ${res.status}`;
        throw new Error(`GasFlow API ${path}: ${detail}`);
      }
      return body as T;
    } finally {
      clearTimeout(timer);
    }
  }

  async listIntegrations(includeInactive = false): Promise<IntegrationConfig[]> {
    const res = await this.request<{ integrations: IntegrationConfig[] }>(
      `/api/v1/integrations?include_inactive=${includeInactive ? "true" : "false"}`
    );
    return res.integrations;
  }

  /** Integrações cujo intervalo de sincronização já venceu. */
  async dueIntegrations(now = new Date()): Promise<IntegrationConfig[]> {
    const all = await this.listIntegrations(false);
    return all.filter((i) => {
      if (!i.last_sync_at) return true;
      const last = new Date(i.last_sync_at).getTime();
      if (Number.isNaN(last)) return true;
      return now.getTime() - last >= i.sync_interval_minutes * 60_000;
    });
  }

  async sendSyncRun(integrationId: string, payload: SyncRunPayload): Promise<unknown> {
    return this.request(`/api/v1/integrations/${integrationId}/sync-run`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async testConnection(integrationId: string): Promise<unknown> {
    return this.request(`/api/v1/integrations/${integrationId}/test-connection`, { method: "POST" });
  }
}
