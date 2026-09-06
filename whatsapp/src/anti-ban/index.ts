/**
 * Anti-ban — Barrel
 *
 * Módulos de higiene de envio (rate limiting, warmup, cooldown,
 * quiet hours e pacing gaussiano). Sem camadas de evasão: o objetivo é
 * volume responsável, não mascarar automação.
 */

export { gaussianRandom, gaussianDelayMs } from './gaussian';
export {
  checkRate,
  recordSend,
  currentUsage,
  type RateCheckResult,
} from './limiter';
export {
  dailyLimit,
  sentToday,
  recordSent,
  hasDailyBudget,
  warmupDayNumber,
} from './warmup';
export { isQuietHour, nextAllowedTime, getConfig, type QuietHoursConfig } from './quiet-hours';
