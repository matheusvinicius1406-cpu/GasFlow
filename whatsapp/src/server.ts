import express from 'express';
import { CONNECT_PAGE_HTML } from './connect-page';
import { closeDb, countLists, insertList } from './db';
import { providerManager } from './provider/provider-manager';
import { router } from './routes';
import { startWorker } from './broadcast';

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
  console.log('[db] Listas padrão criadas.');
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const app = express();
  app.use(express.json());

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

  app.use('/api', router);

  // Error handler
  app.use((err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    console.error('[api] Erro não tratado:', err);
    if (!res.headersSent) res.status(500).json({ error: 'Erro interno.' });
  });

  seedDefaultListsIfEmpty();
  startWorker();

  app.listen(PORT, () => {
    console.log(`[api] Servidor rodando em http://localhost:${PORT}`);
    console.log('[api] POST /api/whatsapp/accounts/:id/start para iniciar uma conta.');
    console.log(`[api] Contas disponíveis: ${providerManager.getAccountIds().join(', ')}`);
  });

  // Graceful shutdown
  let shuttingDown = false;
  const shutdown = async (signal: string) => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`\n[api] Recebido ${signal}, encerrando...`);
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
