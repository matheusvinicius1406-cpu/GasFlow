import type { Express, Request, Response } from 'express';
import { CONNECT_PAGE_HTML } from './connect-page.js';
import { providerManager } from './provider/provider-manager.js';
import { hasValidApiKey } from './auth.js';
import { renderMetrics, METRICS_CONTENT_TYPE } from './metrics.js';

/**
 * SEC-02 — rotas de infraestrutura do gateway.
 *
 * Política de exposição:
 * - /api/health  : liveness público mínimo (ok/uptime). Contas e memória
 *   somente para chamadas autenticadas (o health_check do adapter do backend
 *   envia Bearer e continua recebendo o corpo completo — contrato preservado).
 * - /api/ready   : status operacional público, sem vazar ids de contas.
 * - /connect     : HTML estático público (QR em si só sai de rota protegida).
 * - /metrics     : espelha o padrão METRICS_PUBLIC do backend — aberto só
 *   quando METRICS_PUBLIC=true (dev), senão exige API key (fail-closed).
 */

function isMetricsPublic(): boolean {
  return ['1', 'true'].includes((process.env.METRICS_PUBLIC ?? '').toLowerCase());
}

export function registerInfrastructureRoutes(app: Express, startedAt: number): void {
  // ── Liveness: processo vivo (corpo detalhado só autenticado) ──
  app.get('/api/health', (req: Request, res: Response) => {
    const body: Record<string, unknown> = {
      ok: true,
      uptimeSeconds: Math.round((Date.now() - startedAt) / 1000),
    };
    if (hasValidApiKey(req)) {
      const mem = process.memoryUsage();
      const accounts = providerManager.getAllAccounts();
      body.memory = { rssMb: Math.round(mem.rss / 1024 / 1024), heapUsedMb: Math.round(mem.heapUsed / 1024 / 1024) };
      body.whatsapp = { accounts, total: accounts.length };
    }
    res.json(body);
  });

  // ── Readiness: provider manager inicializado (sem ids de contas) ──
  app.get('/api/ready', (_req: Request, res: Response) => {
    const total = providerManager.getAccountIds().length;
    const ready = total > 0;
    res.status(ready ? 200 : 503).json({ ready, total });
  });

  // Backward compat
  app.get('/connect', (_req: Request, res: Response) => {
    res.type('html').send(CONNECT_PAGE_HTML);
  });

  // ── Prometheus metrics ─────────────────────────────────
  app.get('/metrics', (req: Request, res: Response) => {
    if (!isMetricsPublic() && !hasValidApiKey(req)) {
      res.status(401).json({ error: 'Token de autenticação ausente. Use: Authorization: Bearer <API_KEY>' });
      return;
    }
    void (async () => {
      res.set('Content-Type', METRICS_CONTENT_TYPE);
      res.send(await renderMetrics());
    })().catch((err: unknown) => {
      res.status(500).json({ error: err instanceof Error ? err.message : 'metrics error' });
    });
  });
}
