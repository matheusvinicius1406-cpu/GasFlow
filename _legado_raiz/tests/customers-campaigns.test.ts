/**
 * Testes de customers, preferences, campaigns e list_members.
 * Usa um DATA_DIR temporário para não tocar no banco real.
 */
process.env.DATA_DIR = 'data/test-' + Date.now() + '-' + process.pid + '-' + Math.random().toString(36).slice(2, 8);

import assert from 'node:assert/strict';
import fs from 'node:fs';
import { after, test } from 'node:test';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const dbModule = require('../src/db');
const {
  closeDb,
  db,
  getCustomerById,
  getCustomerByContactId,
  getContactById,
  insertContact,
  promoteContactToCustomer,
  updateCustomerStatus,
  getPreference,
  setOptIn,
  setOptOut,
  isCustomerEligible,
  insertList,
  addCustomerToList,
  removeCustomerFromList,
  getListCustomers,
  countListCustomers,
  insertCampaign,
  getCampaignById,
  createCampaignRecipients,
  getCampaignResults,
  updateCampaignStatus,
  listCampaigns,
} = dbModule;

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

/** Helper: creates a test contact and returns its id. */
function createTestContact(overrides: Record<string, unknown> = {}): number {
  const jid = (overrides.jid as string) ?? `test-${Date.now()}-${Math.random().toString(36).slice(2)}@c.us`;
  insertContact({
    phone: (overrides.phone as string) ?? '5511999999999',
    jid,
    name: (overrides.name as string) ?? 'Fulano Teste',
    pushName: null,
    businessName: null,
    isBusiness: 0,
    isGroup: 0,
  });
  const row = db.prepare('SELECT id FROM contacts WHERE jid = ?').get(jid) as { id: number };
  return row.id;
}

// ---- Customer Tests ----

test('promoteContactToCustomer creates a customer', () => {
  const contactId = createTestContact({ jid: 'cust-1@c.us', name: 'Cliente Um' });
  const customerId = promoteContactToCustomer(contactId);
  assert.equal(typeof customerId, 'number');
  assert.ok(customerId > 0);
  const customer = getCustomerById(customerId);
  assert.ok(customer);
  assert.equal(customer.contact_id, contactId);
  assert.equal(customer.customer_status, 'UNKNOWN');
});

test('promoteContactToCustomer is idempotent', () => {
  const contactId = createTestContact({ jid: 'cust-2@c.us', name: 'Cliente Dois' });
  const id1 = promoteContactToCustomer(contactId);
  const id2 = promoteContactToCustomer(contactId);
  assert.equal(id1, id2);
});

test('updateCustomerStatus changes status', () => {
  const contactId = createTestContact({ jid: 'cust-3@c.us', name: 'Cliente Três' });
  const customerId = promoteContactToCustomer(contactId);
  updateCustomerStatus(customerId, 'CUSTOMER');
  assert.equal(getCustomerById(customerId)?.customer_status, 'CUSTOMER');
  updateCustomerStatus(customerId, 'PROSPECT');
  assert.equal(getCustomerById(customerId)?.customer_status, 'PROSPECT');
});

test('getCustomerByContactId finds customer', () => {
  const contactId = createTestContact({ jid: 'cust-4@c.us', name: 'Cliente Quatro' });
  const customerId = promoteContactToCustomer(contactId);
  const found = getCustomerByContactId(contactId);
  assert.ok(found);
  assert.equal(found.id, customerId);
});

// ---- Preference Tests ----

test('setOptOut marks customer as OPTED_OUT', () => {
  const contactId = createTestContact({ jid: 'pref-1@c.us', name: 'Pref Um' });
  const customerId = promoteContactToCustomer(contactId);
  setOptOut(customerId, 'manual');
  const pref = getPreference(customerId);
  assert.ok(pref);
  assert.equal(pref.marketing_status, 'OPTED_OUT');
  assert.equal(pref.source, 'manual');
});

test('setOptIn marks customer as OPTED_IN', () => {
  const contactId = createTestContact({ jid: 'pref-2@c.us', name: 'Pref Dois' });
  const customerId = promoteContactToCustomer(contactId);
  setOptIn(customerId, 'api');
  const pref = getPreference(customerId);
  assert.ok(pref);
  assert.equal(pref.marketing_status, 'OPTED_IN');
});

test('isCustomerEligible returns true for UNKNOWN (no preference)', () => {
  const contactId = createTestContact({ jid: 'elig-1@c.us', name: 'Eleg Um' });
  const customerId = promoteContactToCustomer(contactId);
  assert.equal(isCustomerEligible(customerId), true);
});

test('isCustomerEligible returns false for OPTED_OUT', () => {
  const contactId = createTestContact({ jid: 'elig-2@c.us', name: 'Eleg Dois' });
  const customerId = promoteContactToCustomer(contactId);
  setOptOut(customerId);
  assert.equal(isCustomerEligible(customerId), false);
});

test('isCustomerEligible returns true for OPTED_IN', () => {
  const contactId = createTestContact({ jid: 'elig-3@c.us', name: 'Eleg Três' });
  const customerId = promoteContactToCustomer(contactId);
  setOptIn(customerId);
  assert.equal(isCustomerEligible(customerId), true);
});

test('isCustomerEligible returns false for BLOCKED', () => {
  const contactId = createTestContact({ jid: 'elig-4@c.us', name: 'Eleg Quatro' });
  const customerId = promoteContactToCustomer(contactId);
  dbModule.upsertPreference(customerId, 'BLOCKED');
  assert.equal(isCustomerEligible(customerId), false);
});

// ---- List Members Tests ----

test('addCustomerToList adds customer to list', () => {
  const listId = insertList('Teste Lista', null);
  const contactId = createTestContact({ jid: 'list-1@c.us', name: 'Lista Um' });
  const customerId = promoteContactToCustomer(contactId);
  const added = addCustomerToList(listId, customerId);
  assert.equal(added, true);
  assert.equal(countListCustomers(listId), 1);
});

test('addCustomerToList is idempotent', () => {
  const listId = insertList('Teste Idempotente', null);
  const contactId = createTestContact({ jid: 'list-2@c.us', name: 'Lista Dois' });
  const customerId = promoteContactToCustomer(contactId);
  addCustomerToList(listId, customerId);
  const addedAgain = addCustomerToList(listId, customerId);
  assert.equal(addedAgain, false);
  assert.equal(countListCustomers(listId), 1);
});

test('removeCustomerFromList removes customer', () => {
  const listId = insertList('Teste Remover', null);
  const contactId = createTestContact({ jid: 'list-3@c.us', name: 'Lista Três' });
  const customerId = promoteContactToCustomer(contactId);
  addCustomerToList(listId, customerId);
  assert.equal(countListCustomers(listId), 1);
  const removed = removeCustomerFromList(listId, customerId);
  assert.equal(removed, true);
  assert.equal(countListCustomers(listId), 0);
});

test('getListCustomers returns customers with contact info', () => {
  const listId = insertList('Teste Listar', null);
  const contactId = createTestContact({ jid: 'list-4@c.us', name: 'Lista Quatro' });
  const customerId = promoteContactToCustomer(contactId);
  addCustomerToList(listId, customerId);
  const customers = getListCustomers(listId);
  assert.equal(customers.length, 1);
  assert.equal(customers[0].id, customerId);
  assert.equal(customers[0].contact?.name, 'Lista Quatro');
});

// ---- Campaign Tests ----

test('insertCampaign creates a campaign', () => {
  const listId = insertList('Campanha Lista', null);
  const id = insertCampaign('Teste Campanha', 'Olá, mensagem de teste!', listId);
  const campaign = getCampaignById(id);
  assert.ok(campaign);
  assert.equal(campaign.name, 'Teste Campanha');
  assert.equal(campaign.message, 'Olá, mensagem de teste!');
  assert.equal(campaign.status, 'DRAFT');
});

test('createCampaignRecipients counts eligible and excluded', () => {
  const listId = insertList('Recipients Lista', null);

  // Create 3 customers in the list
  const c1 = promoteContactToCustomer(createTestContact({ jid: 'recip-1@c.us', name: 'R1' }));
  const c2 = promoteContactToCustomer(createTestContact({ jid: 'recip-2@c.us', name: 'R2' }));
  const c3 = promoteContactToCustomer(createTestContact({ jid: 'recip-3@c.us', name: 'R3' }));
  addCustomerToList(listId, c1);
  addCustomerToList(listId, c2);
  addCustomerToList(listId, c3);

  // Opt out one
  setOptOut(c2);

  const campaignId = insertCampaign('Recipients Test', 'Msg', listId);
  const preview = createCampaignRecipients(campaignId, listId);

  assert.equal(preview.total, 3);
  assert.equal(preview.eligible, 2); // c1 and c3
  assert.equal(preview.optedOut, 1); // c2
});

test('createCampaignRecipients is idempotent', () => {
  const listId = insertList('Idem Recipients', null);
  const c1 = promoteContactToCustomer(createTestContact({ jid: 'idem-1@c.us', name: 'I1' }));
  addCustomerToList(listId, c1);

  const campaignId = insertCampaign('Idem Test', 'Msg', listId);
  const first = createCampaignRecipients(campaignId, listId);
  const second = createCampaignRecipients(campaignId, listId);

  assert.equal(first.eligible, 1);
  assert.equal(second.duplicates, 1); // already exists
  assert.equal(second.eligible, 0);
});

test('getCampaignResults returns correct counts', () => {
  const listId = insertList('Results Lista', null);
  const c1 = promoteContactToCustomer(createTestContact({ jid: 'res-1@c.us', name: 'Res1' }));
  addCustomerToList(listId, c1);

  const campaignId = insertCampaign('Results Test', 'Msg', listId);
  createCampaignRecipients(campaignId, listId);

  const results = getCampaignResults(campaignId);
  assert.equal(results.total, 1);
  assert.equal(results.pending, 1);
  assert.equal(results.sent, 0);
});

test('updateCampaignStatus changes status', () => {
  const listId = insertList('Status Lista', null);
  const campaignId = insertCampaign('Status Test', 'Msg', listId);
  assert.equal(getCampaignById(campaignId)?.status, 'DRAFT');

  updateCampaignStatus(campaignId, 'RUNNING');
  assert.equal(getCampaignById(campaignId)?.status, 'RUNNING');

  updateCampaignStatus(campaignId, 'PAUSED');
  assert.equal(getCampaignById(campaignId)?.status, 'PAUSED');

  updateCampaignStatus(campaignId, 'COMPLETED');
  const completed = getCampaignById(campaignId);
  assert.equal(completed?.status, 'COMPLETED');
  assert.ok(completed?.completed_at);
});

test('listCampaigns returns campaigns in reverse order', () => {
  const listId = insertList('List Campaigns', null);
  const id1 = insertCampaign('Campanha 1', 'Msg1', listId);
  const id2 = insertCampaign('Campanha 2', 'Msg2', listId);
  const campaigns = listCampaigns();
  assert.ok(campaigns.length >= 2);
  // Most recent first
  assert.equal(campaigns[0].id >= campaigns[1].id || campaigns[0].id === id2, true);
});
