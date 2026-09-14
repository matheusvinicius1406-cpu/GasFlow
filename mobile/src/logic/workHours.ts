/**
 * workHours — regra LGPD do roadmap (seção 8): rastreamento SÓ dentro do
 * horário de trabalho, desligamento automático fora dele.
 *
 * Módulo puro (sem imports RN) — testável via node --test.
 */

export interface WorkWindow {
  start: string; // "HH:MM"
  end: string; // "HH:MM"
}

export function parseWindow(config: string | WorkWindow | null | undefined): WorkWindow | null {
  if (!config) return null;
  if (typeof config === "object") {
    return valid(config.start) && valid(config.end) ? { start: config.start, end: config.end } : null;
  }
  const match = /^\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*$/.exec(config);
  if (!match) return null;
  const [, start, end] = match;
  return valid(start) && valid(end) ? { start, end } : null;
}

function valid(hhmm: string): boolean {
  const [h, m] = hhmm.split(":").map(Number);
  return Number.isFinite(h) && Number.isFinite(m) && h >= 0 && h < 24 && m >= 0 && m < 60;
}

function minutesOf(date: Date): number {
  return date.getHours() * 60 + date.getMinutes();
}

function minutesOfHhMm(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

/**
 * Dentro da janela de trabalho? Janela vazia (start===end) nunca coleta.
 * Janela cruzando meia-noite (ex.: 18:00-02:00) suportada.
 * Sem configuração → não coleta (fail-closed: LGPD por padrão).
 */
export function isWithinWorkHours(now: Date, config: string | WorkWindow | null | undefined): boolean {
  const window = parseWindow(config);
  if (!window) return false;
  const start = minutesOfHhMm(window.start);
  const end = minutesOfHhMm(window.end);
  const minutes = minutesOf(now);
  if (start === end) return false; // janela vazia = rastreamento desligado
  if (start < end) return minutes >= start && minutes < end;
  return minutes >= start || minutes < end; // cruza meia-noite
}

/** Janela default do produto: admin ajusta nas Configurações do desktop. */
export const DEFAULT_WORK_WINDOW: WorkWindow = { start: "06:00", end: "20:00" };
