/**
 * api — cliente HTTP do App do Entregador (F2).
 *
 * Funções puras: baseUrl/fetch/token injetados — testável em node --test.
 * Endpoints reais do backend GasFlow:
 *   POST /auth/mobile/login          → { access_token, refresh_token, driver_id }
 *   GET  /driver/deliveries          → { deliveries: [...] }
 *   POST /driver/deliveries/:id/:action  (accept|start|complete|fail)
 *
 * O client_action_id vai no corpo de cada ação (idempotência controlada pela
 * fila offline — offlineQueue.ts deduplica pelo id e marca synced só no 200).
 */

export interface LoginTokens {
  access_token: string;
  refresh_token: string;
  driver_id: string;
}

export interface DeliveryDTO {
  delivery_id: string;
  customer_name: string;
  address: string;
  phone?: string;
  status: string;
}

function baseUrlClean(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "");
}

async function requestJson<T>(fetchFn: typeof fetch, url: string, init: RequestInit): Promise<T> {
  const res = await fetchFn(url, init);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as { error?: string; detail?: string }).error ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function mobileLogin(
  fetchFn: typeof fetch,
  baseUrl: string,
  username: string,
  password: string,
): Promise<LoginTokens> {
  return requestJson<LoginTokens>(fetchFn, `${baseUrlClean(baseUrl)}/auth/mobile/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export async function fetchMyDeliveries(
  fetchFn: typeof fetch,
  baseUrl: string,
  token: string,
): Promise<DeliveryDTO[]> {
  const data = await requestJson<{ deliveries: DeliveryDTO[] }>(fetchFn, `${baseUrlClean(baseUrl)}/driver/deliveries`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return data.deliveries ?? [];
}

export type DeliveryAction = "accept" | "start" | "complete" | "fail";

/** Envia uma ação da fila. Lança em falha — o OfflineQueue decide o backoff. */
export async function postDeliveryAction(
  fetchFn: typeof fetch,
  baseUrl: string,
  token: string,
  args: { deliveryId: string; action: DeliveryAction; clientActionId: string; payload?: Record<string, unknown> },
): Promise<void> {
  const { deliveryId, action, clientActionId, payload = {} } = args;
  await requestJson<unknown>(fetchFn, `${baseUrlClean(baseUrl)}/driver/deliveries/${deliveryId}/${action}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ client_action_id: clientActionId, ...payload }),
  });
}
