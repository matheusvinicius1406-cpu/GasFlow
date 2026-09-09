/**
 * Fetcher — baixa HTML do site da revenda.
 *
 * Ferramenta de integração para o PRÓPRIO site do usuário (ou com autorização
 * dele): usa apenas as credenciais configuradas pelo dono. Não há bypass de
 * proteção anti-bot nem evasão — se o site bloquear, a integração falha de
 * forma explícita.
 */

export interface FetchResult {
  url: string;
  status: number;
  html: string;
}

export interface FetchAuth {
  type: "none" | "basic" | "token" | "cookie";
  config?: Record<string, string> | null;
}

const UA = "GasFlow-Integration-Agent/1.0 (+https://gasflow.com.br; integracao autorizada pelo proprietario)";

export async function fetchHtml(url: string, auth: FetchAuth, timeoutMs = 20000): Promise<FetchResult> {
  const headers: Record<string, string> = {
    "User-Agent": UA,
    Accept: "text/html,application/xhtml+xml",
  };

  if (auth.type === "basic" && auth.config) {
    const cred = Buffer.from(`${auth.config.username ?? ""}:${auth.config.password ?? ""}`).toString("base64");
    headers["Authorization"] = `Basic ${cred}`;
  } else if (auth.type === "token" && auth.config?.token) {
    headers["Authorization"] = `Bearer ${auth.config.token}`;
  } else if (auth.type === "cookie" && auth.config?.cookie) {
    headers["Cookie"] = auth.config.cookie;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { headers, signal: controller.signal, redirect: "follow" });
    const html = await res.text();
    return { url, status: res.status, html };
  } finally {
    clearTimeout(timer);
  }
}

/** Tenta a URL configurada e, na falta dela, caminhos comuns de pedidos. */
export async function discoverOrdersPage(
  baseUrl: string,
  auth: FetchAuth,
  configuredPath?: string | null
): Promise<FetchResult> {
  const base = baseUrl.replace(/\/+$/, "");
  const candidates: string[] = [];
  if (configuredPath) candidates.push(`${base}${configuredPath.startsWith("/") ? configuredPath : `/${configuredPath}`}`);
  candidates.push(
    `${base}/pedidos`,
    `${base}/orders`,
    `${base}/vendas`,
    `${base}/minhas-vendas`,
    `${base}/admin/pedidos`,
    `${base}/admin/orders`
  );

  const errors: string[] = [];
  for (const url of candidates) {
    try {
      const result = await fetchHtml(url, auth);
      if (result.status === 200 && result.html.trim().length > 0) {
        return result;
      }
      errors.push(`${url} → HTTP ${result.status}`);
    } catch (e) {
      errors.push(`${url} → ${(e as Error).message}`);
    }
  }
  throw new Error(`Nenhuma página de pedidos respondendo. Tentativas: ${errors.join("; ")}`);
}
