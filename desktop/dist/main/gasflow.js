// @ts-nocheck
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Cliente HTTP para o backend GasFlow — mesmos endpoints do agente
 * (listIntegrations / sync-run / test-connection) mais health check.
 * Autenticação: token de serviço via Bearer (mesma confiança do WhatsApp).
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.GasFlowClient = void 0;
class GasFlowClient {
    baseUrl;
    token;
    timeoutMs;
    fetchFn;
    constructor(opts) {
        this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
        this.token = opts.token;
        this.timeoutMs = opts.timeoutMs ?? 20_000;
        this.fetchFn = opts.fetchFn ?? fetch;
    }
    async request(reqPath, init) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeoutMs);
        try {
            const res = await this.fetchFn(`${this.baseUrl}${reqPath}`, {
                ...init,
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${this.token}`,
                    ...(init?.headers ?? {}),
                },
                signal: controller.signal,
            });
            const body = (await res.json().catch(() => ({})));
            if (!res.ok) {
                throw new Error(`GasFlow API ${reqPath}: ${body.detail ?? `HTTP ${res.status}`}`);
            }
            return body;
        }
        finally {
            clearTimeout(timer);
        }
    }
    async health() {
        try {
            await this.request("/api/v1/integrations");
            return { ok: true, detail: "conectado" };
        }
        catch (e) {
            return { ok: false, detail: e.message };
        }
    }
    async listIntegrations(includeInactive = false) {
        const res = await this.request(`/api/v1/integrations?include_inactive=${includeInactive ? "true" : "false"}`);
        return res.integrations;
    }
    async sendSyncRun(integrationId, payload) {
        return this.request(`/api/v1/integrations/${integrationId}/sync-run`, {
            method: "POST",
            body: JSON.stringify(payload),
        });
    }
    // ── Conversas WhatsApp (gateway do backend) ─────────────
    async listConversations(limit = 50, offset = 0) {
        return this.request(`/api/v1/whatsapp/conversations?limit=${limit}&offset=${offset}`);
    }
    async getConversation(id) {
        return this.request(`/api/v1/whatsapp/conversations/${id}`);
    }
    async takeoverConversation(id, operator) {
        return this.request(`/api/v1/whatsapp/conversations/${id}/takeover`, {
            method: "POST",
            body: JSON.stringify({ operator }),
        });
    }
    async releaseConversation(id) {
        return this.request(`/api/v1/whatsapp/conversations/${id}/release`, { method: "POST" });
    }
    /** Resposta manual do operador — o backend grava e devolve o outbound;
     *  a entrega real acontece via WhatsAppBridge.sendMessage. */
    async replyConversation(id, text) {
        const res = await this.request(`/api/v1/whatsapp/conversations/${id}/reply`, { method: "POST", body: JSON.stringify({ text }) });
        return { outbound_to: res.outbound?.recipient_phone, text: res.outbound?.text };
    }
}
exports.GasFlowClient = GasFlowClient;
//# sourceMappingURL=gasflow.js.map
