/**
 * Quiet Hours — janela noturna sem envios de campanha.
 *
 * Por padrão bloqueia envios entre 22:00 e 07:00 (hora local do servidor).
 * Config via env:
 * - WA_QUIET_HOURS_START (0–23, default 22)
 * - WA_QUIET_HOURS_END   (0–23, default 7)
 * - WA_QUIET_HOURS_ENABLED (default true)
 */

const START = Number(process.env.WA_QUIET_HOURS_START ?? 22);
const END = Number(process.env.WA_QUIET_HOURS_END ?? 7);
const ENABLED = process.env.WA_QUIET_HOURS_ENABLED !== 'false';

export interface QuietHoursConfig {
  startHour: number;
  endHour: number;
  enabled: boolean;
}

export function getConfig(): QuietHoursConfig {
  return { startHour: START, endHour: END, enabled: ENABLED };
}

/** True se o horário atual (ou o informado) está dentro da janela silenciosa. */
export function isQuietHour(now: Date = new Date()): boolean {
  if (!ENABLED) return false;
  const h = now.getHours();
  if (START === END) return false; // janela vazia
  if (START < END) return h >= START && h < END;
  // Janela atravessa meia-noite (ex.: 22 → 7)
  return h >= START || h < END;
}

/** Próximo timestamp (ms) em que envios podem retomar. */
export function nextAllowedTime(now: Date = new Date()): number {
  if (!ENABLED) return now.getTime();
  const next = new Date(now);
  next.setHours(END, 0, 0, 0);
  if (next.getTime() <= now.getTime()) next.setDate(next.getDate() + 1);
  return next.getTime();
}
