/**
 * Warmup Progressivo — rampa diária de volume por conta.
 *
 * Dias 1–7 após o primeiro envio de uma conta, limita o volume diário:
 * 50 → 100 → 200 → 350 → 500 → 700 → 1000. Após o dia 7, o limite diário
 * pleno se aplica (WA_DAILY_CAP).
 *
 * Persistência: tabela SQLite send_counters (sobrevive a restarts, sem
 * dependência externa — o serviço usa SQLite local, não o Redis do compose).
 */

import { db } from '../db';

const WARMUP_LADDER = [50, 100, 200, 350, 500, 700, 1000];

/** Garante que a tabela de contadores exista (idempotente). */
function ensureTable(): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS send_counters (
      account_id TEXT NOT NULL,
      day        TEXT NOT NULL, -- 'YYYY-MM-DD' (UTC)
      sent_count INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (account_id, day)
    );
  `);
}

function todayUtc(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

function firstSendDayUtc(accountId: string): string | null {
  ensureTable();
  const row = db
    .prepare('SELECT MIN(day) AS first_day FROM send_counters WHERE account_id = ?')
    .get(accountId) as { first_day: string | null } | undefined;
  return row?.first_day ?? null;
}

/** Dias decorridos (UTC) desde o primeiro envio registrado da conta. */
export function warmupDayNumber(accountId: string, now: Date = new Date()): number {
  const first = firstSendDayUtc(accountId);
  if (!first) return 0; // conta nova — nenhum envio registrado ainda
  const diffMs = Date.parse(`${todayUtc(now)}T00:00:00Z`) - Date.parse(`${first}T00:00:00Z`);
  return Math.max(0, Math.floor(diffMs / 86_400_000));
}

/** Limite diário efetivo: degrau da rampa de warmup ou o cap pleno. */
export function dailyLimit(accountId: string, fullDailyCap: number, now: Date = new Date()): number {
  const day = warmupDayNumber(accountId, now);
  if (day >= WARMUP_LADDER.length) return fullDailyCap;
  // Antes do primeiro envio (day 0), já tratamos como dia 1 da rampa.
  return WARMUP_LADDER[day];
}

/** Enviados hoje (UTC) pela conta. */
export function sentToday(accountId: string, now: Date = new Date()): number {
  ensureTable();
  const row = db
    .prepare('SELECT sent_count FROM send_counters WHERE account_id = ? AND day = ?')
    .get(accountId, todayUtc(now)) as { sent_count: number } | undefined;
  return Number(row?.sent_count ?? 0);
}

/** Incrementa o contador diário (chamar após envio bem-sucedido). */
export function recordSent(accountId: string, now: Date = new Date()): void {
  ensureTable();
  db.prepare(
    `INSERT INTO send_counters (account_id, day, sent_count) VALUES (?, ?, 1)
     ON CONFLICT(account_id, day) DO UPDATE SET sent_count = sent_count + 1`,
  ).run(accountId, todayUtc(now));
}

/** Restam envios hoje dentro do limite efetivo? */
export function hasDailyBudget(accountId: string, fullDailyCap: number, now: Date = new Date()): boolean {
  return sentToday(accountId, now) < dailyLimit(accountId, fullDailyCap, now);
}
