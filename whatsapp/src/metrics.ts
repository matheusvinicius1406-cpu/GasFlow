/**
 * Prometheus metrics do serviço WhatsApp.
 *
 * Endpoint: GET /metrics (formato text/plain do Prometheus).
 * Métricas:
 * - whatsapp_messages_sent_total{account}          — envios bem-sucedidos
 * - whatsapp_messages_failed_total{account,reason} — falhas de envio
 * - whatsapp_account_connected{account,engine}     — 1 conectado / 0 não
 * - whatsapp_reconnect_attempts_total{account}     — tentativas de reconexão
 * Plus default process metrics (GC, heap, event loop lag).
 */

import client from 'prom-client';

const register = new client.Registry();
client.collectDefaultMetrics({ register });

export const messagesSentTotal = new client.Counter({
  name: 'whatsapp_messages_sent_total',
  help: 'Mensagens enviadas com sucesso',
  labelNames: ['account'] as const,
  registers: [register],
});

export const messagesFailedTotal = new client.Counter({
  name: 'whatsapp_messages_failed_total',
  help: 'Falhas de envio',
  labelNames: ['account', 'reason'] as const,
  registers: [register],
});

export const accountConnected = new client.Gauge({
  name: 'whatsapp_account_connected',
  help: '1 se a conta está conectada, 0 caso contrário',
  labelNames: ['account', 'engine'] as const,
  registers: [register],
});

export const reconnectAttemptsTotal = new client.Counter({
  name: 'whatsapp_reconnect_attempts_total',
  help: 'Tentativas de reconexão agendadas',
  labelNames: ['account'] as const,
  registers: [register],
});

/** Renderiza todas as métricas no formato de exposição do Prometheus. */
export async function renderMetrics(): Promise<string> {
  return register.metrics();
}

/** Content-Type oficial do formato Prometheus. */
export const METRICS_CONTENT_TYPE = client.register.contentType;
