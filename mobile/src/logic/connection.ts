/**
 * connection — fallback de conexão do App do Entregador (prompt 2.2):
 *   1. LAN (WiFi do depósito)  → http://{ip}:{port}
 *   2. Nuvem (relay Fly.io)    → https://relay
 *   3. Offline                 → fila local
 *
 * Módulo puro: fetch injetado. Decisão baseada em health check (3s timeout).
 */

export interface ConnectionTargets {
  lan?: { baseUrl: string } | null;
  /** relayToken: token compartilhado do relay (X-Relay-Token) p/ o rastreamento na nuvem (F2.5). */
  cloud?: { baseUrl: string; relayToken?: string } | null;
}

export type ConnectionMode = "lan" | "cloud" | "offline";

export interface ResolvedConnection {
  mode: ConnectionMode;
  baseUrl: string | null;
}

const PROBE_TIMEOUT_MS = 3_000;

async function probe(baseUrl: string, fetchFn: typeof fetch): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetchFn(`${baseUrl.replace(/\/+$/, "")}/health`, { signal: controller.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Resolve o alvo ativo: tenta LAN → nuvem → offline.
 * `prefer` permite re-tentar LAN periodicamente sem degradar a UX.
 */
export async function resolveConnection(
  targets: ConnectionTargets,
  fetchFn: typeof fetch,
): Promise<ResolvedConnection> {
  if (targets.lan?.baseUrl && (await probe(targets.lan.baseUrl, fetchFn))) {
    return { mode: "lan", baseUrl: targets.lan.baseUrl };
  }
  if (targets.cloud?.baseUrl && (await probe(targets.cloud.baseUrl, fetchFn))) {
    return { mode: "cloud", baseUrl: targets.cloud.baseUrl };
  }
  return { mode: "offline", baseUrl: null };
}
