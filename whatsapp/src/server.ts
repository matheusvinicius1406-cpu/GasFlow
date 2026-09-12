import 'dotenv/config';
import express from 'express';
import { CONNECT_PAGE_HTML } from './connect-page';
import { closeDb, countLists, insertList } from './db';
import { providerManager } from './provider/provider-manager';
import { router } from './routes';
import { startWorker } from './broadcast';
import { forwardIncomingMessage, type RawIncomingMessage } from './incoming';
import { logger } from './log';
import { requireAuth } from './auth';
import { renderMetrics, METRICS_CONTENT_TYPE } from './metrics';

const PORT = Number(process.env.PORT ?? 3000);

function seedDefaultListsIfEmpty(): void {
  if (countLists() > 0) return;
  const defaults: Array<{ name: string; description: string }> = [
    { name: 'Clientes', description: 'Todos os clientes' },
    { name: 'Clientes Gás', description: 'Clientes de gás' },
    { name: 'Clientes Água', description: 'Clientes de água' },
    { name: 'Clientes Ativos', description: 'Clientes ativos' },
    { name: 'Clientes Inativos', description: 'Clientes inativos' },
    { name: 'Clientes Frequentes', description: 'Clientes frequentes' },
    { name: 'Clientes Novos', description: 'Clientes novos' },
    { name: 'Restaurantes', description: 'Restaurantes' },
    { name: 'Escolas', description: 'Escolas' },
    { name: 'Empresas', description: 'Empresas' },
  ];
  for (const l of defaults) insertList(l.name, l.description);
  logger.info('db.default_lists_created');
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const app = express();
  // 30mb: a rota de mídia aceita 25MB base64 (+overhead JSON) — o default
  // de 100KB rejeitava a maioria das mídias com 413 antes de chegar à rota.
  app.use(express.json({ limit: '30mb' }));
  app.use(express.urlencoded({ extended: true, limit: '30mb' }));

  // ── Liveness: process is alive ──────────────────────────
  app.get('/api/health', (_req, res) => {
    const mem = process.memoryUsage();
    const accounts = providerManager.getAllAccounts();
    res.json({
      ok: true,
      uptimeSeconds: Math.round((Date.now() - startedAt) / 1000),
      memory: { rssMb: Math.round(mem.rss / 1024 / 1024), heapUsedMb: Math.round(mem.heapUsed / 1024 / 1024) },
      whatsapp: { accounts, total: accounts.length },
    });
  });

  // ── Readiness: provider manager initialized ─────────────
  app.get('/api/ready', (_req, res) => {
    const accountIds = providerManager.getAccountIds();
    const ready = accountIds.length > 0;
    res.status(ready ? 200 : 503).json({
      ready,
      accounts: accountIds,
      total: accountIds.length,
    });
  });

  // Backward compat
  app.get('/connect', (_req, res) => {
    res.type('html').send(CONNECT_PAGE_HTML);
  });

  // ── Prometheus metrics ─────────────────────────────────
  app.get('/metrics', async (_req, res) => {
    try {
      res.set('Content-Type', METRICS_CONTENT_TYPE);
      res.send(await renderMetrics());
    } catch (err) {
      res.status(500).json({ error: err instanceof Error ? err.message : 'metrics error' });
    }
  });

  app.use('/api', router);

  // Alias raiz /send → /api/whatsapp/accounts/:id/messages — contrato do
  // WhatsAppSendBridge do backend (POST {service_url}/send com accountId no
  // body). Sem isso, TODA automação (FASE 14) falhava com 404.
  // Express 5: app._router foi removido — despacha direto pelo Router da API
  // (Router é um RequestHandler chamável) com a URL relativa ao mount /api.
  app.post('/send', express.json({ limit: '1mb' }), (req: express.Request, res: express.Response, next: express.NextFunction) => {
    req.url = `/whatsapp/accounts/${encodeURIComponent(String(req.body?.accountId ?? 'primary'))}/messages`;
    (req as unknown as { body: unknown }).body = {
      recipient: req.body?.recipient,
      message: req.body?.text,
      idempotency_key: req.body?.idempotencyKey,
    };
    router(req, res, next);
  });

  // Error handler
  app.use((err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    logger.error('api.unhandled_error', { error: err instanceof Error ? err.message : String(err) });
    if (!res.headersSent) res.status(500).json({ error: 'Erro interno.' });
  });

  // ── Incoming messages → backend (AI pipeline) ──────────
  for (const account of providerManager.getAllAccounts()) {
    const accountId = account.id;
    providerManager.getAccount(accountId)?.onMessage((raw: unknown) => {
      void forwardIncomingMessage(accountId, raw as RawIncomingMessage);
    });
  }
  logger.info('incoming.bridge.wired', { accounts: providerManager.getAccountIds() });

  seedDefaultListsIfEmpty();
  startWorker();

  // Push de contatos → CRM (backend). Dispara no boot (após conectar) e
  // fica disponível manualmente via POST /api/whatsapp/crm-sync.
  // Import tardio: falha de rede nunca derruba o serviço.
  const { syncAllToCrm } = await import('./crm-sync');
  const crmSyncTimer = setTimeout(() => {
    void syncAllToCrm().catch(() => { /* tolerante */ });
  }, 30_000); // aguarda contas conectarem
  crmSyncTimer.unref?.();

  app.post('/api/whatsapp/crm-sync', requireAuth, (req: express.Request, res: express.Response) => {
    const accountId = String(req.body?.accountId || 'primary');
    void import('./crm-sync').then(({ syncAccountToCrm }) => syncAccountToCrm(accountId))
      .then((result) => res.json(result))
      .catch((err) => res.status(500).json({ error: err instanceof Error ? err.message : 'crm-sync failed' }));
  });

  app.listen(PORT, () => {
    logger.info('api.started', { port: PORT, accounts: providerManager.getAccountIds() });
  });

  // Graceful shutdown
  let shuttingDown = false;
  const shutdown = async (signal: string) => {
    if (shuttingDown) return;
    shuttingDown = true;
    logger.info('api.shutdown_requested', { signal });
    try {
      await providerManager.stopAll();
    } finally {
      closeDb();
      process.exit(0);
    }
  };
  process.on('SIGINT', () => void shutdown('SIGINT'));
  process.on('SIGTERM', () => void shutdown('SIGTERM'));
}

void main();
