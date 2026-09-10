/**
 * Log estruturado (JSON lines) do serviço WhatsApp.
 *
 * Saída: uma linha JSON por evento, legível por qualquer agregador
 * (Grafana/Loki, CloudWatch, etc.).
 */

import pino from 'pino';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LEVEL_ORDER: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };
const MIN_LEVEL: LogLevel = (process.env.WA_LOG_LEVEL as LogLevel) || 'info';
const pinoLogger = pino({ level: MIN_LEVEL });

function emit(level: LogLevel, event: string, fields: Record<string, unknown> = {}): void {
  if (LEVEL_ORDER[level] < LEVEL_ORDER[MIN_LEVEL]) return;
  pinoLogger[level]({ service: 'gasflow-whatsapp', event, ...fields }, event);
}

export const logger = {
  debug: (event: string, fields?: Record<string, unknown>) => emit('debug', event, fields),
  info: (event: string, fields?: Record<string, unknown>) => emit('info', event, fields),
  warn: (event: string, fields?: Record<string, unknown>) => emit('warn', event, fields),
  error: (event: string, fields?: Record<string, unknown>) => emit('error', event, fields),
};
