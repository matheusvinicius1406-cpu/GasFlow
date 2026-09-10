import electronLog from "electron-log";

/**
 * Logger do main process: escreve em electron-log (arquivo em userData) e
 * espelha cada linha para o renderer via webContents (console de logs da UI).
 */
export type LogLevel = "info" | "warn" | "error";
type RendererSender = (channel: string, payload: { level: LogLevel; scope: string; message: string; ts: number }) => void;

let send: RendererSender | null = null;

/** Registra a função que entrega linhas ao renderer (chamado no webContents did-finish-load). */
export function setRendererSender(fn: RendererSender): void {
  send = fn;
}

export function logLine(level: LogLevel, scope: string, message: string): void {
  const text = `[${new Date().toISOString()}] [${scope}] ${message}`;
  if (level === "error") electronLog.error(text);
  else if (level === "warn") electronLog.warn(text);
  else electronLog.info(text);
  send?.("gasflow:log", { level, scope, message: text, ts: Date.now() });
}

export const logger = {
  info: (scope: string, message: string) => logLine("info", scope, message),
  warn: (scope: string, message: string) => logLine("warn", scope, message),
  error: (scope: string, message: string) => logLine("error", scope, message),
};
