/**
 * Rate Limiter — caps de volume por conta (minute/hour) + cooldown por destinatário.
 *
 * Janelas deslizantes em SQLite (mesma store do serviço — sem dependência do
 * Redis do compose, que pertence ao backend). Base é a tabela send_history,
 * indexada por (account_id, sent_at) e (account_id, recipient, sent_at).
 *
 * Config (env):
 * - WA_MINUTE_CAP (default 20)
 * - WA_HOURLY_CAP (default 200)
 * - WA_RECIPIENT_COOLDOWN_MIN (default 60)
 */

import { db } from '../db';

const MINUTE_CAP = Math.max(1, Number(process.env.WA_MINUTE_CAP ?? 20));
const HOURLY_CAP = Math.max(1, Number(process.env.WA_HOURLY_CAP ?? 200));
const RECIPIENT_COOLDOWN_MIN = Math.max(0, Number(process.env.WA_RECIPIENT_COOLDOWN_MIN ?? 60));

const MINUTE_WINDOW_MS = 60_000;
const HOUR_WINDOW_MS = 3_600_000;

export interface RateCheckResult {
  allowed: boolean;
  reason?: 'minute_cap' | 'hourly_cap' | 'recipient_cooldown';
  /** Quando o envio pode ser tentado novamente (epoch ms), se bloqueado. */
  retryAtMs?: number;
}

function countSince(accountId: string, sinceMs: number): number {
  const row = db
    .prepare('SELECT COUNT(*) AS cnt FROM send_history WHERE account_id = ? AND sent_at_ms >= ?')
    .get(accountId, sinceMs) as { cnt: number };
  return Number(row.cnt);
}

function lastSendToRecipientMs(accountId: string, recipient: string): number | null {
  const row = db
    .prepare(
      'SELECT MAX(sent_at_ms) AS last_ms FROM send_history WHERE account_id = ? AND recipient = ?',
    )
    .get(accountId, recipient) as { last_ms: number | null };
  return row?.last_ms ?? null;
}

/** Verifica todos os limites para um envio hipotético agora. */
export function checkRate(
  accountId: string,
  recipient: string,
  nowMs: number = Date.now(),
): RateCheckResult {
  if (countSince(accountId, nowMs - MINUTE_WINDOW_MS) >= MINUTE_CAP) {
    return { allowed: false, reason: 'minute_cap', retryAtMs: nowMs + MINUTE_WINDOW_MS };
  }
  if (countSince(accountId, nowMs - HOUR_WINDOW_MS) >= HOURLY_CAP) {
    return { allowed: false, reason: 'hourly_cap', retryAtMs: nowMs + MINUTE_WINDOW_MS };
  }
  if (RECIPIENT_COOLDOWN_MIN > 0) {
    const last = lastSendToRecipientMs(accountId, recipient);
    if (last !== null) {
      const cooldownMs = RECIPIENT_COOLDOWN_MIN * 60_000;
      if (nowMs - last < cooldownMs) {
        return { allowed: false, reason: 'recipient_cooldown', retryAtMs: last + cooldownMs };
      }
    }
  }
  return { allowed: true };
}

/** Grava um envio bem-sucedido no histórico (base para as janelas). */
export function recordSend(
  accountId: string,
  recipient: string,
  messageId: string | undefined,
  nowMs: number = Date.now(),
): void {
  db.prepare(
    'INSERT INTO send_history (account_id, recipient, sent_at_ms, provider_message_id) VALUES (?, ?, ?, ?)',
  ).run(accountId, recipient, nowMs, messageId ?? null);
}

/** Contagem corrente nas janelas — para observabilidade/endpoint de status. */
export function currentUsage(accountId: string, nowMs: number = Date.now()): {
  lastMinute: number;
  lastHour: number;
  minuteCap: number;
  hourlyCap: number;
} {
  return {
    lastMinute: countSince(accountId, nowMs - MINUTE_WINDOW_MS),
    lastHour: countSince(accountId, nowMs - HOUR_WINDOW_MS),
    minuteCap: MINUTE_CAP,
    hourlyCap: HOURLY_CAP,
  };
}
