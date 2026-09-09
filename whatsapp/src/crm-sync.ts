/**
 * CRM Sync — empurra contatos do WhatsApp para o CRM do backend.
 *
 * Origem dos contatos: catálogo 1:1 do engine (getJids no Baileys;
 * getContacts no wwebjs, já normalizado pelo provider-manager).
 * Destino: POST {GASFLOW_BACKEND_URL}/clients/contacts/sync-batch com
 * header X-GasFlow-Key (mesma chave do bridge de entrada).
 *
 * Tolerante a falhas: erro de rede nunca derruba o serviço; lotes de 100.
 */

import { providerManager } from './provider/provider-manager';
import { logger } from './log';

const BACKEND_URL = (process.env.GASFLOW_BACKEND_URL || '').replace(/\/+$/, '');
const SERVICE_KEY = process.env.GASFLOW_SERVICE_KEY || process.env.MARCOS_GAS_API_KEY || '';

const BATCH_SIZE = Number(process.env.BATCH_SYNC_SIZE || 100);
const TIMEOUT_MS = 15_000;

export interface CrmSyncResult {
  sent: number;
  batches: number;
  ok: boolean;
  error?: string;
}

/** Coleta contatos 1:1 da conta (formato provider-neutral) e empurra ao CRM. */
export async function syncAccountToCrm(accountId: string): Promise<CrmSyncResult> {
  if (!BACKEND_URL) {
    return { sent: 0, batches: 0, ok: false, error: 'GASFLOW_BACKEND_URL não configurado' };
  }
  const account = providerManager.getAccount(accountId);
  if (!account || !account.isConnected()) {
    return { sent: 0, batches: 0, ok: false, error: `Conta ${accountId} não conectada` };
  }

  const contacts = await account.getContacts();
  const oneToOne = contacts.filter((c) => !c.isGroup && c.phone);
  const payload = oneToOne.map((c) => ({
    telefone: c.phone,
    nome: c.name || c.pushName || null,
    is_whatsapp: true,
  }));

  let sent = 0;
  let batches = 0;
  for (let i = 0; i < payload.length; i += BATCH_SIZE) {
    const batch = payload.slice(i, i + BATCH_SIZE);
    try {
      const res = await fetch(`${BACKEND_URL}/clients/contacts/sync-batch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(SERVICE_KEY ? { 'X-GasFlow-Key': SERVICE_KEY } : {}),
        },
        body: JSON.stringify({ contacts: batch }),
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
      if (!res.ok) {
        logger.warn('crm-sync.batch.rejected', { account: accountId, status: res.status, batch: batch.length });
        continue;
      }
      sent += batch.length;
      batches += 1;
    } catch (err) {
      logger.warn('crm-sync.batch.failed', {
        account: accountId,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  logger.info('crm-sync.done', { account: accountId, contacts: payload.length, sent, batches });
  return { sent, batches, ok: batches > 0 || payload.length === 0 };
}

/** Sync de todas as contas conectadas (chamado no boot e pela rota manual). */
export async function syncAllToCrm(): Promise<Record<string, CrmSyncResult>> {
  const results: Record<string, CrmSyncResult> = {};
  for (const accountId of providerManager.getAccountIds()) {
    const account = providerManager.getAccount(accountId);
    if (account?.isConnected()) {
      results[accountId] = await syncAccountToCrm(accountId);
    }
  }
  return results;
}
