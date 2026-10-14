/**
 * Regressão: dedupe NÃO pode perder dados de customer.
 * - Consolidação por nome preserva customer, preferência (opt-out) e list_members.
 * - Remoção de @lid migra o customer para o contato de mesmo telefone.
 * - @lid com customer e sem herdeiro é mantido (nunca apagar dados de cliente).
 */
process.env.DATA_DIR = 'data/test-' + Date.now() + '-' + process.pid + '-' + Math.random().toString(36).slice(2, 8);

import assert from 'node:assert/strict';
import fs from 'node:fs';
import { after, test } from 'node:test';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const {
  closeDb,
  db,
  insertContact,
  insertList,
  addCustomerToList,
  promoteContactToCustomer,
  getCustomerByContactId,
  getPreference,
  setOptOut,
  countListCustomers,
  deleteLidContacts,
  dedupeByName,
} = require('../src/db');

after(() => {
  try {
    closeDb();
  } catch {
    // ignore
  }
  try {
    fs.rmSync(process.env.DATA_DIR as string, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  } catch {
    // ignore
  }
});

function insertTestContact(opts: { jid: string; phone: string | null; name: string }): number {
  insertContact({
    phone: opts.phone,
    jid: opts.jid,
    name: opts.name,
    pushName: null,
    businessName: null,
    isBusiness: 0,
    isGroup: 0,
  });
  const row = db.prepare('SELECT id FROM contacts WHERE jid = ?').get(opts.jid) as { id: number };
  return row.id;
}

test('dedupe por nome preserva customer, opt-out e membership da linha removida', () => {
  const keepId = insertTestContact({ jid: 'dedupe-keep@c.us', phone: '5511900000001', name: 'Maria Silva' });
  const dupeId = insertTestContact({ jid: 'dedupe-dupe@c.us', phone: '5511900000002', name: 'maria silva ' });

  const customerId = promoteContactToCustomer(dupeId, 'CUSTOMER');
  setOptOut(customerId, 'whatsapp');
  const listId = insertList('Lista Dedupe', null);
  addCustomerToList(listId, customerId);

  const { result: merged } = dedupeByName();
  assert.ok(merged >= 1, 'grupo duplicado deve ser consolidado');

  // Linha duplicada removida, linha mantida existe.
  assert.equal(getCustomerByContactId(dupeId), undefined);
  const kept = getCustomerByContactId(keepId);
  assert.ok(kept, 'customer deve sobreviver apontando para a linha mantida');
  assert.equal(kept.customer_status, 'CUSTOMER');

  // Preferência de marketing preservada (opt-out NUNCA pode se perder).
  const pref = getPreference(kept.id);
  assert.equal(pref?.marketing_status, 'OPTED_OUT');
  assert.equal(pref?.source, 'whatsapp');

  // Membership de lista preservada.
  assert.equal(countListCustomers(listId), 1);
});

test('dedupe por nome: quando AMBAS as linhas têm customer, funde preservando o opt-out mais restritivo', () => {
  const keepId = insertTestContact({ jid: 'dedupe-2-keep@c.us', phone: '5511900000003', name: 'Joao Souza' });
  const dupeId = insertTestContact({ jid: 'dedupe-2-dupe@c.us', phone: '5511900000004', name: 'JOAO SOUZA' });

  const keepCustomer = promoteContactToCustomer(keepId, 'PROSPECT'); // sem preferência
  const dupeCustomer = promoteContactToCustomer(dupeId, 'CUSTOMER');
  setOptOut(dupeCustomer, 'api');

  const listId = insertList('Lista Dedupe 2', null);
  addCustomerToList(listId, dupeCustomer);

  dedupeByName();

  // Customer mantido (linha dona da verdade) continua existindo.
  const merged = getCustomerByContactId(keepId);
  assert.ok(merged);
  assert.equal(merged.id, keepCustomer);

  // Opt-out da duplicata vence a ausência de preferência do mantido.
  assert.equal(getPreference(keepCustomer)?.marketing_status, 'OPTED_OUT');

  // Membership migra para o customer sobrevivente.
  assert.equal(countListCustomers(listId), 1);

  // O customer duplicado foi removido (sem órfãos).
  assert.equal(getCustomerByContactId(dupeId), undefined);
  const orphans = db.prepare('SELECT COUNT(*) AS c FROM customers WHERE contact_id NOT IN (SELECT id FROM contacts)').get() as { c: number };
  assert.equal(orphans.c, 0);
});

test('@lid com customer migra para o contato de mesmo telefone', () => {
  const realId = insertTestContact({ jid: '5511900000005@c.us', phone: '5511900000005', name: 'Carlos' });
  const lidId = insertTestContact({ jid: '5511900000005@lid', phone: '5511900000005', name: null });

  const customerId = promoteContactToCustomer(lidId, 'CUSTOMER');
  setOptOut(customerId, 'manual');

  const { removed, migrated, kept } = deleteLidContacts();

  assert.ok(removed >= 1, '@lid sem customer equivalente deve sair');
  assert.ok(migrated >= 1, 'customer do @lid deve ser migrado');
  assert.equal(kept, 0);

  const migratedRow = getCustomerByContactId(realId);
  assert.ok(migratedRow, 'customer deve apontar para o contato real de mesmo telefone');
  assert.equal(migratedRow.id, customerId, 'mesmo customer, apenas repontado');
  assert.equal(getPreference(customerId)?.marketing_status, 'OPTED_OUT');
});

test('@lid COM customer e SEM telefone equivalente é mantido (sem perda de dados)', () => {
  const lidId = insertTestContact({ jid: '9988776655443322@lid', phone: null, name: 'Sem Herdeiro' });
  const customerId = promoteContactToCustomer(lidId, 'CUSTOMER');

  const { removed, kept } = deleteLidContacts();

  assert.equal(kept, 1, '@lid com customer e sem herdeiro deve ser mantido');
  assert.ok(getCustomerByContactId(lidId), 'customer deve continuar vinculado');
  assert.ok(getCustomerByContactId(lidId)?.id === customerId);

  // Linhas @lid sem customer continuam sendo removidas; o protegido segue mantido.
  insertTestContact({ jid: '1122334455667788@lid', phone: null, name: 'Descartável' });
  const second = deleteLidContacts();
  assert.ok(second.removed >= 1, '@lid sem customer continua sendo removido');
  assert.equal(second.kept, 1, 'o @lid protegido continua mantido');
  assert.ok(getCustomerByContactId(lidId), 'customer continua de pé');
});
