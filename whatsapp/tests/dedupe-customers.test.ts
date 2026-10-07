/**
 * Regressão (whatsapp service): dedupe NÃO pode perder dados de customer.
 *
 * IMPORTANTE: DATA_DIR temporário precisa estar definido ANTES do import do
 * db.ts — por isso o `await import()` dinâmico (pacote ESM).
 */
process.env.DATA_DIR =
  'data/test-' + Date.now() + '-' + process.pid + '-' + Math.random().toString(36).slice(2, 8);

import assert from 'node:assert/strict';
import fs from 'node:fs';
import { after, describe, it } from 'node:test';

const {
  db,
  closeDb,
  insertContact,
  insertList,
  addCustomerToList,
  addContactToList,
  promoteContactToCustomer,
  getCustomerByContactId,
  getPreference,
  setOptOut,
  countListCustomers,
  deleteLidContacts,
  dedupeByName,
  insertCampaign,
  createCampaignRecipients,
  updateCampaignStatus,
  getCampaignById,
  markRecipientCancelled,
  getCampaignResults,
} = await import('../src/db.js');

after(() => {
  try {
    closeDb();
  } catch {
    // já fechado
  }
  try {
    fs.rmSync(process.env.DATA_DIR as string, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  } catch {
    // melhor esforço
  }
});

let seq = 0;

function makeContact(opts: { jid: string; phone: string | null; name?: string | null }): number {
  seq += 1;
  insertContact({
    phone: opts.phone,
    jid: opts.jid,
    name: opts.name === undefined ? `Contact ${seq}` : opts.name,
    pushName: null,
    businessName: null,
    isBusiness: 0,
    isGroup: 0,
  });
  const row = db.prepare('SELECT id FROM contacts WHERE jid = ?').get(opts.jid) as { id: number };
  return row.id;
}

describe('dedupe preserva dados de customer', () => {
  it('consolidação por nome mantém customer, opt-out e membership', () => {
    const keepId = makeContact({ jid: `dk-keep-${seq + 1}@c.us`, phone: '5511900000001', name: 'Maria Silva' });
    const dupeId = makeContact({ jid: `dk-dupe-${seq + 1}@c.us`, phone: '5511900000002', name: 'maria silva ' });

    const customerId = promoteContactToCustomer(dupeId, 'CUSTOMER');
    setOptOut(customerId, 'whatsapp');
    const listId = insertList(`DK Lista ${seq}`, null);
    addCustomerToList(listId, customerId);

    const { result: merged } = dedupeByName();
    assert.ok(merged >= 1, 'grupo duplicado deve ser consolidado');

    assert.equal(getCustomerByContactId(dupeId), undefined, 'duplicata removida');
    const kept = getCustomerByContactId(keepId);
    assert.ok(kept, 'customer sobrevive apontando para a linha mantida');
    assert.equal(getPreference(kept.id)?.marketing_status, 'OPTED_OUT', 'opt-out preservado');
    assert.equal(countListCustomers(listId), 1, 'membership preservada');
  });

  it('quando AMBAS as linhas têm customer, o opt-out mais restritivo vence', () => {
    const keepId = makeContact({ jid: `dk2-keep-${seq + 1}@c.us`, phone: '5511900000003', name: 'Joao Souza' });
    const dupeId = makeContact({ jid: `dk2-dupe-${seq + 1}@c.us`, phone: '5511900000004', name: 'JOAO SOUZA' });

    const keepCustomer = promoteContactToCustomer(keepId, 'PROSPECT');
    const dupeCustomer = promoteContactToCustomer(dupeId, 'CUSTOMER');
    setOptOut(dupeCustomer, 'api');

    const listId = insertList(`DK2 Lista ${seq}`, null);
    addCustomerToList(listId, dupeCustomer);

    dedupeByName();

    const merged = getCustomerByContactId(keepId);
    assert.ok(merged);
    assert.equal(merged.id, keepCustomer, 'customer mantido é o sobrevivente');
    assert.equal(getPreference(keepCustomer)?.marketing_status, 'OPTED_OUT', 'consentimento da duplicata vence');
    assert.equal(countListCustomers(listId), 1, 'membership migra');
    assert.equal(getCustomerByContactId(dupeId), undefined);
    const orphans = db
      .prepare('SELECT COUNT(*) AS c FROM customers WHERE contact_id NOT IN (SELECT id FROM contacts)')
      .get() as { c: number };
    assert.equal(orphans.c, 0, 'sem customer órfão');
  });

  it('@lid com customer migra para o contato de mesmo telefone', () => {
    const realId = makeContact({ jid: `5511900000005@c.us`, phone: '5511900000005', name: 'Carlos' });
    const lidId = makeContact({ jid: `5511900000005@lid`, phone: '5511900000005', name: null });

    const customerId = promoteContactToCustomer(lidId, 'CUSTOMER');
    setOptOut(customerId, 'manual');

    const { removed, migrated, kept } = deleteLidContacts();
    assert.ok(removed >= 1, '@lid sem customer equivalente sai');
    assert.ok(migrated >= 1, 'customer do @lid é migrado');
    assert.equal(kept, 0);

    const migratedRow = getCustomerByContactId(realId);
    assert.ok(migratedRow, 'customer aponta para o contato real');
    assert.equal(migratedRow.id, customerId, 'mesmo customer, repontado');
    assert.equal(getPreference(customerId)?.marketing_status, 'OPTED_OUT', 'preferência migra junto');
  });

  it('@lid COM customer e SEM telefone equivalente é mantido (sem perda de dados)', () => {
    const lidId = makeContact({ jid: `${seq + 1}9988776655443322@lid`, phone: null, name: 'Sem Herdeiro' });
    const customerId = promoteContactToCustomer(lidId, 'CUSTOMER');

    const { removed, kept } = deleteLidContacts();
    assert.equal(kept, 1, '@lid com customer e sem herdeiro é mantido');
    assert.equal(removed, 0);
    assert.ok(getCustomerByContactId(lidId), 'customer continua vinculado');
    assert.equal(getCustomerByContactId(lidId)?.id, customerId);

    // @lid sem customer continua sendo removido; o protegido segue mantido.
    makeContact({ jid: `${seq + 1}1122334455667788@lid`, phone: null, name: 'Descartável' });
    const second = deleteLidContacts();
    assert.ok(second.removed >= 1, '@lid sem customer é removido');
    assert.equal(second.kept, 1, 'o protegido continua mantido');
  });

  it('list_contacts da duplicata migra para a linha mantida', () => {
    const keepId = makeContact({ jid: `dk3-keep-${seq + 1}@c.us`, phone: '5511900000006', name: 'Padaria Real' });
    const dupeId = makeContact({ jid: `dk3-dupe-${seq + 1}@c.us`, phone: '5511900000007', name: 'padaria real' });

    const listId = insertList(`DK3 Lista ${seq}`, null);
    addContactToList(listId, dupeId);

    dedupeByName();

    const rows = db
      .prepare('SELECT contact_id FROM list_contacts WHERE list_id = ?')
      .all(listId) as Array<{ contact_id: number }>;
    assert.deepEqual(
      rows.map((r) => r.contact_id),
      [keepId],
      'membership de contato migra para a linha mantida',
    );
  });
});

describe('campanha', () => {
  it('pause/resume não zera started_at', () => {
    const contactId = makeContact({ jid: `camp-${seq + 1}@c.us`, phone: '5511900000008', name: 'Campanha' });
    const customerId = promoteContactToCustomer(contactId, 'CUSTOMER');
    const listId = insertList(`Camp Lista ${seq}`, null);
    addCustomerToList(listId, customerId);
    const campaignId = insertCampaign(`Camp ${seq}`, 'Olá!', listId);
    createCampaignRecipients(campaignId, listId);

    updateCampaignStatus(campaignId, 'RUNNING');
    const startedAt = getCampaignById(campaignId)?.started_at;
    assert.ok(startedAt, 'started_at definido no primeiro start');

    updateCampaignStatus(campaignId, 'PAUSED');
    updateCampaignStatus(campaignId, 'RUNNING');
    assert.equal(getCampaignById(campaignId)?.started_at, startedAt, 'retomada preserva started_at');
  });

  it('CANCELLED (não elegível) não conta como falha de envio', () => {
    const contactId = makeContact({ jid: `cx-${seq + 1}@c.us`, phone: '5511900000009', name: 'Cancelado' });
    const customerId = promoteContactToCustomer(contactId, 'CUSTOMER');
    const listId = insertList(`CX Lista ${seq}`, null);
    addCustomerToList(listId, customerId);
    const campaignId = insertCampaign(`CX ${seq}`, 'Oi', listId);
    createCampaignRecipients(campaignId, listId);
    updateCampaignStatus(campaignId, 'RUNNING');

    markRecipientCancelled(campaignId, customerId, 'Excluded: No valid phone number');
    const results = getCampaignResults(campaignId);
    assert.equal(results.cancelled, 1);
    assert.equal(results.failed, 0, 'CANCELLED não vira FAILED');
  });
});
