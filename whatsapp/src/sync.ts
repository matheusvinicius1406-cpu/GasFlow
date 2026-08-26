import {
  db,
  findContactByJid,
  findContactByPhone,
  insertContact,
  rebindContactJid,
  updateContact,
} from './db';
import { normalizePhone } from './normalize';
import type { WhatsAppContact } from './provider/types';

export interface SyncResult {
  fetched: number;
  inserted: number;
  updated: number;
}

/** Forma neutra de um contato pronta para persistência. */
export interface ContactValues {
  phone: string | null;
  jid: string;
  name: string | null;
  pushName: string | null;
  businessName: string | null;
  isBusiness: number;
  isGroup: number;
}

/** Mapeia o contato normalizado do provider para os valores de persistência. */
export function mapToValues(contact: WhatsAppContact): ContactValues {
  return {
    jid: contact.jid,
    phone: contact.isGroup ? null : normalizePhone(contact.phone ?? contact.jid.split('@')[0]),
    name: contact.name,
    pushName: contact.pushName,
    businessName: contact.businessName,
    isBusiness: contact.isBusiness ? 1 : 0,
    isGroup: contact.isGroup ? 1 : 0,
  };
}

/**
 * Upsert idempotente em transação única.
 * - Dedupe #1: jid (coluna UNIQUE).
 * - Dedupe #2: telefone normalizado (mesmo número sob outro jid reutiliza a linha).
 * Rodar várias vezes nunca cria duplicatas; apenas atualiza metadados.
 */
export function upsertContacts(valuesList: ContactValues[]): SyncResult {
  let inserted = 0;
  let updated = 0;

  db.exec('BEGIN IMMEDIATE');
  try {
    for (const values of valuesList) {
      const byJid = findContactByJid(values.jid);
      if (byJid) {
        updateContact(byJid.id, values);
        updated += 1;
        continue;
      }

      if (values.phone) {
        const byPhone = findContactByPhone(values.phone);
        if (byPhone) {
          rebindContactJid(values.jid, byPhone.id);
          updateContact(byPhone.id, values);
          updated += 1;
          continue;
        }
      }

      insertContact(values);
      inserted += 1;
    }
    db.exec('COMMIT');
  } catch (err) {
    db.exec('ROLLBACK');
    throw err;
  }

  return { fetched: valuesList.length, inserted, updated };
}

/** Sincroniza todos os contatos do provider para o banco. Idempotente.
 * 
 * IMPORTANTE: sync NÃO cria customers automaticamente.
 * contacts ≠ customers. Um contato do WhatsApp não é automaticamente
 * um cliente do Marcos Gás. A promoção para customer deve ser explícita
 * via POST /api/customers/:contactId/promote.
 */
export async function runSync(): Promise<SyncResult> {
  // Import tardio evita dependência circular (provider -> nada de sync).
  const { providerManager } = await import('./provider/provider-manager');
  const primaryAccount = providerManager.getAccount("primary"); if (!primaryAccount) throw new Error("Primary account not found"); const waContacts = await primaryAccount.getContacts();
  return upsertContacts(waContacts.map(mapToValues));
}
