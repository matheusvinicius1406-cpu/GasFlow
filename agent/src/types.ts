/**
 * Tipos compartilhados do agente de integração.
 */

export interface IntegrationConfig {
  id: string;
  name: string;
  base_url: string;
  orders_path?: string | null;
  auth_type: "none" | "basic" | "token" | "cookie";
  auth_config?: Record<string, string> | null;
  field_mapping?: Record<string, string> | null;
  selectors?: Record<string, string> | null;
  sync_interval_minutes: number;
  last_sync_at?: string | null;
}

export interface RawItem {
  product_name: string;
  product_codigo?: string;
  quantity: number;
  unit_price?: number | null;
  raw?: string;
}

/** Pedido extraído e normalizado — formato aceito pelo backend. */
export interface NormalizedOrder {
  external_id: string;
  client_name: string;
  client_phone: string;
  client_email: string;
  address: string;
  items: RawItem[];
  total?: number | null;
  delivery_fee?: number | null;
  payment_method?: string | null;
  status: string;
  notes: string;
}

export interface AgentError {
  external_ref?: string;
  message: string;
}

export interface SyncRunPayload {
  orders: NormalizedOrder[];
  errors: AgentError[];
  trigger: "agent";
}
