/**
 * api — cliente HTTP do App do Entregador.
 *
 * O entregador NÃO tem mais login próprio: autentica na **auth principal**
 * (`POST /auth/login`), herdando o gate de `must_change_password` no HTTP e no
 * WebSocket. As rotas do app vivem em `/driver/*` (namespace novo, escopado por
 * tenant + driver). O login antigo (`/auth/mobile/login`, `/api/v1/driver/*`)
 * continua no backend marcado `# LEGACY`, mas o app migrado não o usa.
 *
 * Funções puras: baseUrl/fetch/token injetados — testável em node --test.
 *
 *   POST /auth/login            → { access_token, refresh_token, user, role }
 *   GET  /auth/me               → { id, username, role, must_change_password }
 *   POST /auth/change-password  → limpa a flag de troca
 *   GET  /driver/deliveries     → { deliveries: [...] }
 *   GET  /driver/me             → perfil + janela LGPD + cadência
 */

// ── Gate de troca de senha ───────────────────────────────────

/**
 * Lançada quando o backend recusa uma rota por troca de senha pendente
 * (`403` + `X-GasFlow-Password-Change-Required: 1`, ou `detail` equivalente
 * quando o header não atravessa o proxy). O app trata como **estado**, não erro.
 */
export class PasswordChangeRequiredError extends Error {
  constructor() {
    super("Password change required");
    this.name = "PasswordChangeRequiredError";
  }
}

function passwordChangeRequired(res: Response, detail: unknown): boolean {
  if (res.status !== 403) return false;
  if (res.headers?.get?.("X-GasFlow-Password-Change-Required") === "1") return true;
  return (detail as { detail?: string } | null)?.detail === "Password change required";
}

// ── Tipos ────────────────────────────────────────────────────

export interface OperatorUser {
  id: string;
  username: string;
  email?: string;
  display_name?: string;
  must_change_password?: boolean;
}

export interface LoginResult {
  access_token: string;
  refresh_token: string;
  /** Compat: backends antigos devolvem só `token` (opaco). */
  token?: string;
  role: string;
  tenant_id: string;
  user: OperatorUser;
}

export interface MeDTO {
  id: string;
  username: string;
  display_name?: string;
  role: string;
  tenant_id: string;
  permissions?: string[];
  must_change_password: boolean;
}

export interface DeliveryDTO {
  delivery_id: string;
  customer_name: string;
  address: string;
  phone?: string;
  status: string;
}

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
  /** Fase 7.5: distância percorrida hoje (km), calculada do histórico. */
  today_distance_km?: number;
}

function baseUrlClean(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "");
}

async function requestJson<T>(fetchFn: typeof fetch, url: string, init: RequestInit): Promise<T> {
  const res = await fetchFn(url, init);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    if (passwordChangeRequired(res, detail)) throw new PasswordChangeRequiredError();
    throw new Error((detail as { error?: string; detail?: string }).error ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

// ── Sessão (auth principal) ──────────────────────────────────

export async function operatorLogin(
  fetchFn: typeof fetch,
  baseUrl: string,
  username: string,
  password: string,
): Promise<LoginResult> {
  return requestJson<LoginResult>(fetchFn, `${baseUrlClean(baseUrl)}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // platform=mobile: a sessão fica marcada como app do entregador (B5).
    body: JSON.stringify({ username, password, platform: "mobile" }),
  });
}

export async function fetchMe(fetchFn: typeof fetch, baseUrl: string, token: string): Promise<MeDTO> {
  return requestJson<MeDTO>(fetchFn, `${baseUrlClean(baseUrl)}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function changePassword(
  fetchFn: typeof fetch,
  baseUrl: string,
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<{ success: boolean }> {
  return requestJson<{ success: boolean }>(fetchFn, `${baseUrlClean(baseUrl)}/auth/change-password`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

// ── Entregas ─────────────────────────────────────────────────

function formatAddress(addr: unknown): string {
  if (!addr || typeof addr !== "object") return typeof addr === "string" ? addr : "";
  const a = addr as Record<string, unknown>;
  const line = [a.street, a.number].filter(Boolean).join(", ");
  const rest = [line, a.neighborhood, a.city].filter(Boolean).join(" — ");
  return rest;
}

/** Normaliza o DeliveryRecord do backend (`id`, `address` objeto) para o DTO do app. */
function toDeliveryDTO(raw: Record<string, unknown>): DeliveryDTO {
  return {
    delivery_id: String(raw.id ?? raw.delivery_id ?? ""),
    customer_name: String(raw.customer_name ?? ""),
    address: formatAddress(raw.address),
    phone: (raw.phone ?? raw.customer_phone) as string | undefined,
    status: String(raw.status ?? ""),
  };
}

export async function fetchMyDeliveries(fetchFn: typeof fetch, baseUrl: string, token: string): Promise<DeliveryDTO[]> {
  const data = await requestJson<{ deliveries: Record<string, unknown>[] }>(
    fetchFn,
    `${baseUrlClean(baseUrl)}/driver/deliveries`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  return (data.deliveries ?? []).map(toDeliveryDTO);
}

export async function fetchDriverMe(fetchFn: typeof fetch, baseUrl: string, token: string): Promise<DriverMeDTO> {
  return requestJson<DriverMeDTO>(fetchFn, `${baseUrlClean(baseUrl)}/driver/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

/** URL do WebSocket de realtime para o canal `driver:{driver_id}`. */
export function driverWsUrl(baseUrl: string, token: string): string {
  const clean = baseUrlClean(baseUrl).replace(/^http/, "ws");
  return `${clean}/ws?token=${encodeURIComponent(token)}`;
}

// ── Ações de entrega ─────────────────────────────────────────
//
// TODO (próxima fase): mover para `/driver/*` (auth principal). Hoje estas
// rotas são as legadas `/api/v1/driver/*`, que só aceitam a sessão/JWT antigo;
// o backend precisa expor accept/start/complete/fail no namespace novo antes
// de o app migrado usá-las. A tela de rota (lista) já usa o namespace novo.

export type DeliveryAction = "accept" | "start" | "complete" | "fail";

/** Envia uma ação da fila. Lança em falha — o OfflineQueue decide o backoff. */
export async function postDeliveryAction(
  fetchFn: typeof fetch,
  baseUrl: string,
  token: string,
  args: { deliveryId: string; action: DeliveryAction; clientActionId: string; payload?: Record<string, unknown> },
): Promise<void> {
  const { deliveryId, action, clientActionId, payload = {} } = args;
  const clean = baseUrlClean(baseUrl);
  const path =
    action === "accept"
      ? `${clean}/api/v1/driver/deliveries/${deliveryId}/accept`
      : action === "start"
        ? `${clean}/api/v1/driver/deliveries/${deliveryId}/start`
        : action === "complete"
          ? `${clean}/api/v1/driver/deliveries/${deliveryId}/complete`
          : `${clean}/api/v1/driver/deliveries/${deliveryId}/fail`;
  await requestJson<unknown>(fetchFn, path, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ client_action_id: clientActionId, ...payload }),
  });
}

// ── Rastreamento ─────────────────────────────────────────────

/** Posição no formato do ingest. */
export interface DriverLocationBody {
  latitude: number;
  longitude: number;
  accuracy?: number;
  speed?: number;
  bearing?: number;
}

/**
 * Ingest LAN da posição.
 *
 * TODO (próxima fase): mover para `/driver/location` (auth principal). Hoje é
 * a rota legada `/api/v1/driver/location`, que só aceita a sessão/JWT antigo.
 */
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
