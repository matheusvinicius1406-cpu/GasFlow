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

// ── Rastreamento (F2.5) ──────────────────────────────────────

/** Espelha DriverMeResponse do backend (driver_api.py). */
export interface DriverMeDTO {
  driver_id: string;
  name: string;
  phone: string;
  status: string;
  active: boolean;
  tenant_id: string;
  tracking_interval_seconds: number;
  /** Janela LGPD "HH:MM-HH:MM" — mesma regra reforçada no ingest (403 fora dela). */
  work_hours?: string | null;
}

export async function fetchDriverMe(fetchFn: typeof fetch, baseUrl: string, token: string): Promise<DriverMeDTO> {
  return requestJson<DriverMeDTO>(fetchFn, `${baseUrlClean(baseUrl)}/api/v1/driver/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

/** Posição no formato do ingest LAN (/api/v1/driver/location). */
export interface DriverLocationBody {
  latitude: number;
  longitude: number;
  accuracy?: number;
  speed?: number;
  bearing?: number;
}

/** LAN: POST direto no backend com o JWT do entregador (throttle 10s no servidor). */
export async function postDriverLocation(
  fetchFn: typeof fetch,
  baseUrl: string,
  token: string,
  body: DriverLocationBody,
): Promise<{ success: boolean; throttled?: boolean }> {
  return requestJson<{ success: boolean; throttled?: boolean }>(
    fetchFn,
    `${baseUrlClean(baseUrl)}/api/v1/driver/location`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

/** Posição no formato do relay (LocationPing — relay/app/main.py). */
export interface RelayPosition {
  lat: number;
  lng: number;
  speed?: number | null;
  heading?: number | null;
  accuracy?: number | null;
  recorded_at?: string | null;
}

/** Nuvem: POST no relay (fora da LAN) — auth por token compartilhado do relay. */
export async function postDriverLocationRelay(
  fetchFn: typeof fetch,
  relayBaseUrl: string,
  relayToken: string,
  args: { driverId: string; tenantId: string; positions: RelayPosition[] },
): Promise<{ accepted: number; delivered_to_desktop?: boolean }> {
  const { driverId, tenantId, positions } = args;
  return requestJson<{ accepted: number; delivered_to_desktop?: boolean }>(
    fetchFn,
    `${baseUrlClean(relayBaseUrl)}/driver/location`,
    {
      method: "POST",
      headers: { "X-Relay-Token": relayToken, "Content-Type": "application/json" },
      body: JSON.stringify({ driver_id: driverId, tenant_id: tenantId, positions }),
    },
  );
}
