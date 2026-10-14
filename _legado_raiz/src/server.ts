import { createApp } from './app';
import { closeDb, countLists, insertList } from './db';
import { whatsappProvider } from './provider/wwebjs-provider';
import { startWorker, stopWorker } from './broadcast';

const PORT = Number(process.env.PORT ?? 3000);

/**
 * Seeds the example lists once, when the table is still empty.
 * Lists are fully editable/deletable afterwards — nothing in the
 * business logic depends on these specific names.
 */
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
  const app = createApp(startedAt);

  seedDefaultListsIfEmpty();

  // Start broadcast worker (processes campaign message queue)
  startWorker();

  app.listen(PORT, () => {
    console.log(`[api] Servidor rodando em http://localhost:${PORT}`);
    console.log('[api] POST /api/whatsapp/start para iniciar a sessão.');
  });

  // Clean shutdown keeps the stored WhatsApp session for the next boot.
  let shuttingDown = false;
  const shutdown = async (signal: string) => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`\n[api] Recebido ${signal}, encerrando...`);
    stopWorker();
    try {
      await whatsappProvider.stop();
    } finally {
      closeDb();
      process.exit(0);
    }
  };
  process.on('SIGINT', () => void shutdown('SIGINT'));
  process.on('SIGTERM', () => void shutdown('SIGTERM'));
}

void main();
