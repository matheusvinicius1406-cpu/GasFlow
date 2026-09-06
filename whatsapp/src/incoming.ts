/**
 * Incoming Message Bridge — whatsapp → backend (GasFlow).
 *
 * Encaminha mensagens RECEBIDAS no WhatsApp para o backend
 * (`POST /whatsapp/incoming`), que roda o pipeline de IA do GasFlow.
 * Se o backend responder com `outbound_text` + `outbound_to`, a resposta
 * é enviada de volta pelo mesmo número/account (loop fechado: bot responde).
 *
 * Config (env):
 * - GASFLOW_BACKEND_URL — base do backend (ex.: http://backend:8000). Vazio = bridge desligado.
 * - GASFLOW_SERVICE_KEY  — chave compartilhada enviada como `X-GasFlow-Key`
 *                          (mesmo valor de MARCOS_GAS_API_KEY do backend).
 *
 * O forwarder é tolerante a falhas: nunca derruba o serviço WhatsApp.
 */

import { providerManager } from './provider/provider-manager';
import { logger } from './log';

const BACKEND_URL = (process.env.GASFLOW_BACKEND_URL || '').replace(/\/+$/, '');
const SERVICE_KEY = process.env.GASFLOW_SERVICE_KEY || process.env.MARCOS_GAS_API_KEY || '';

const MAX_FORWARD_ATTEMPTS = 3;
const FORWARD_BASE_DELAY_MS = 1_000;

/** Forma mínima da mensagem bruta do whatsapp-web.js que o bridge consome. */
export interface RawIncomingMessage {
  id?: { _serialized?: string } | string;
  from?: string;
  fromMe?: boolean;
  /** Mensagens de grupo vêm com author preenchido — ignoramos ruído de grupo. */
  author?: string;
  body?: string;
  type?: string;
  timestamp?: number;
}

export interface IncomingForwardOptions {
  backendUrl: string;
  serviceKey: string;
  maxAttempts?: number;
  /** Injeta o envio de resposta (default: providerManager.sendMessage). */
  sendReply?: (accountId: string, to: string, text: string) => Promise<unknown>;
  /** Injeta o transporte HTTP (default: global fetch). */
  fetchImpl?: typeof fetch;
}

export function createIncomingForwarder(opts: IncomingForwardOptions) {
  const maxAttempts = opts.maxAttempts ?? MAX_FORWARD_ATTEMPTS;
  const sendReply = opts.sendReply ?? ((accountId: string, to: string, text: string) => {
    const account = providerManager.getAccount(accountId);
    if (!account) return Promise.resolve({ success: false, error: 'ACCOUNT_NOT_FOUND' });
    return account.sendMessage(to, { text });
  });
  const fetchImpl = opts.fetchImpl ?? fetch;
  const url = opts.backendUrl.replace(/\/+$/, '');

  if (!url) {
    logger.warn('incoming.bridge.disabled', { reason: 'GASFLOW_BACKEND_URL não configurado' });
  }

  /** Converte a mensagem bruta para o contrato IncomingMessageRequest do backend. */
  function buildPayload(accountId: string, raw: RawIncomingMessage) {
    const from = raw.from ?? '';
    const senderPhone = from.replace(/@c\.us$/, '').replace(/@g\.us$/, '');
    const messageId =
      (typeof raw.id === 'object' && raw.id ? raw.id._serialized : raw.id as string) || `local-${Date.now()}`;
    return {
      account_id: accountId,
      sender_phone: senderPhone,
      provider_message_id: messageId,
      text: raw.body ?? '',
      message_type: raw.type ? String(raw.type).toUpperCase() : 'TEXT',
      from_me: false,
      timestamp: raw.timestamp ? new Date(Number(raw.timestamp) * 1000).toISOString() : undefined,
    };
  }

  async function attemptForward(accountId: string, payload: ReturnType<typeof buildPayload>): Promise<boolean> {
    let lastError = '';
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const res = await fetchImpl(`${url}/whatsapp/incoming`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(opts.serviceKey ? { 'X-GasFlow-Key': opts.serviceKey } : {}),
          },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          const data = (await res.json().catch(() => null)) as {
            outbound_text?: string | null;
            outbound_to?: string | null;
          } | null;
          if (data?.outbound_text && data?.outbound_to) {
            await sendReply(accountId, data.outbound_to, data.outbound_text);
            logger.info('incoming.reply.sent', { account: accountId, to: data.outbound_to });
          }
          return true;
        }
        lastError = `HTTP ${res.status}`;
        if (res.status >= 400 && res.status < 500) {
          // Erro de contrato/auth — retentar não ajuda.
          logger.warn('incoming.forward.rejected', { account: accountId, status: res.status });
          return false;
        }
      } catch (err) {
        lastError = err instanceof Error ? err.message : String(err);
      }
      if (attempt < maxAttempts) {
        await new Promise((r) => setTimeout(r, FORWARD_BASE_DELAY_MS * 2 ** (attempt - 1)));
      }
    }
    logger.warn('incoming.forward.failed', { account: accountId, error: lastError, attempts: maxAttempts });
    return false;
  }

  /** Ponto de entrada usado pelos listeners do provider-manager. */
  return async function forward(accountId: string, raw: RawIncomingMessage): Promise<void> {
    if (!url) return;
    if (!raw || raw.fromMe) return;
    // Mensagens de grupo (author presente) — fora do escopo do bot 1:1.
    if (raw.author) return;
    const from = raw.from ?? '';
    if (!from || !from.includes('@')) return;

    const payload = buildPayload(accountId, raw);
    await attemptForward(accountId, payload);
  };
}

/** Forwarder padrão (config de ambiente). */
export const forwardIncomingMessage = createIncomingForwarder({
  backendUrl: BACKEND_URL,
  serviceKey: SERVICE_KEY,
});
