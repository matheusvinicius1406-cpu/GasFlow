import express from 'express';
import { CONNECT_PAGE_HTML } from './connect-page';
import { whatsappProvider } from './provider/wwebjs-provider';
import { router } from './routes';

/**
 * Monta a aplicação Express (rotas, 404 JSON e error handler central).
 * Separado do bootstrap (server.ts) para permitir testes HTTP de ponta a
 * ponta sem subir o processo nem tocar no provider do WhatsApp.
 */
export function createApp(startedAt: number = Date.now()): express.Express {
  const app = express();
  app.use(express.json());

  // Health check do processo (padrão WAHA /health): liveness + resumo da sessão.
  app.get('/api/health', (_req, res) => {
    const mem = process.memoryUsage();
    res.json({
      ok: true,
      uptimeSeconds: Math.round((Date.now() - startedAt) / 1000),
      memory: { rssMb: Math.round(mem.rss / 1024 / 1024), heapUsedMb: Math.round(mem.heapUsed / 1024 / 1024) },
      whatsapp: whatsappProvider.getStatus(),
    });
  });

  // Página de conexão com o QR Code oficial do WhatsApp Web.
  app.get('/connect', (_req, res) => {
    res.type('html').send(CONNECT_PAGE_HTML);
  });

  app.use('/api', router);

  // Rota de API desconhecida -> JSON (evita o HTML padrão do Express).
  app.use('/api', (_req, res) => {
    res.status(404).json({ error: 'Rota não encontrada.' });
  });

  // Basic error handler so thrown errors become JSON responses.
  app.use(
    (
      err: unknown,
      _req: express.Request,
      res: express.Response,
      _next: express.NextFunction,
    ) => {
      // Body-parser: JSON malformado é erro do cliente (400), não do servidor.
      if (err instanceof SyntaxError && 'status' in err && (err as { status?: number }).status === 400) {
        if (!res.headersSent) {
          res.status(400).json({ error: 'JSON inválido no corpo da requisição.' });
        }
        return;
      }
      console.error('[api] Erro não tratado:', err);
      if (!res.headersSent) {
        res.status(500).json({ error: 'Erro interno.' });
      }
    },
  );

  return app;
}
