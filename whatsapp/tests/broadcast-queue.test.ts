/**
 * Regressão (whatsapp service): worker de broadcast drena destinatários não
 * elegíveis sem provider conectado, devolve o claim sem queimar retry e a
 * política de proteção ignora CANCELLED.
 *
 * DATA_DIR temporário definido ANTES do import dinâmico (pacote ESM).
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
  promoteContactToCustomer,
  setOptOut,
  insertCampaign,
  createCampaignRecipients,
  updateCampaignStatus,
  getCampaignById,
  getCampaignResults,
} = await import('../src/db.js');

const { processNext, shouldActivateProtection } = await import('../src/broadcast.js');

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

function makeCustomer(opts: { jid: string; phone: string | null }): number {
  seq += 1;
  insertContact({
    phone: opts.phone,
    jid: opts.jid,
    name: `BC ${seq}`,
    pushName: null,
    businessName: null,
    isBusiness: 0,
    isGroup: 0,
  });
  const contact = db.prepare('SELECT id FROM contacts WHERE jid = ?').get(opts.jid) as { id: number };
  return promoteContactToCustomer(contact.id, 'CUSTOMER');
}

function setupCampaign(customerIds: number[]): number {
  seq += 1;
  const listId = insertList(`BC Lista ${seq}`, null);
  for (const cid of customerIds) addCustomerToList(listId, cid);
  const campaignId = insertCampaign(`BC Camp ${seq}`, 'Mensagem de teste', listId);
  createCampaignRecipients(campaignId, listId);
  return campaignId;
}

describe('broadcast worker (sem conta conectada)', () => {
  it('drena não elegíveis e devolve o claim do elegível sem queimar retry', async () => {
    // Ordem importa: claim ordena por customer_id.
    const noPhone = makeCustomer({ jid: `bc-nophone-${seq + 1}@lid`, phone: null });
    const optedOut = makeCustomer({ jid: `bc-optout-${seq + 1}@c.us`, phone: '5511940000001' });
    const eligible = makeCustomer({ jid: `bc-eligible-${seq + 1}@c.us`, phone: '5511940000002' });

    const campaignId = setupCampaign([noPhone, optedOut, eligible]);
    setOptOut(optedOut, 'test');
    updateCampaignStatus(campaignId, 'RUNNING');

    await processNext();

    const results = getCampaignResults(campaignId);
    assert.equal(results.cancelled, 2, 'não elegíveis viram CANCELLED');
    assert.equal(results.failed, 0, 'CANCELLED não conta como falha de envio');
    assert.equal(results.pending, 1, 'elegível segue PENDING (claim devolvido)');
    assert.equal(results.processing, 0, 'nada fica preso em PROCESSING');

    const pending = db
      .prepare("SELECT customer_id, attempts FROM campaign_recipients WHERE campaign_id = ? AND status = 'PENDING'")
      .all(campaignId) as Array<{ customer_id: number; attempts: number }>;
    assert.equal(pending.length, 1);
    assert.equal(pending[0].customer_id, eligible);
    assert.equal(pending[0].attempts, 0, 'unclaim desfaz o incremento de attempts');

    assert.equal(
      getCampaignById(campaignId)?.status,
      'RUNNING',
      'campanha não completa com pendente remanescente',
    );

    // Encerra aqui para não interferir nos próximos testes (fila é global).
    updateCampaignStatus(campaignId, 'CANCELLED');
  });

  it('campanha 100% não elegível é COMPLETED mesmo sem conta conectada', async () => {
    const noPhone = makeCustomer({ jid: `bc-only-${seq + 1}@lid`, phone: null });
    const campaignId = setupCampaign([noPhone]);
    updateCampaignStatus(campaignId, 'RUNNING');

    await processNext();

    const results = getCampaignResults(campaignId);
    assert.equal(results.cancelled, 1);
    assert.equal(results.pending, 0);
    assert.equal(getCampaignById(campaignId)?.status, 'COMPLETED');
  });
});

describe('política de proteção', () => {
  function campaignWithStatuses(statuses: string[]): number {
    seq += 1;
    const listId = insertList(`Prot Lista ${seq}`, null);
    const customerIds = statuses.map((_, i) =>
      makeCustomer({ jid: `bc-prot-${seq + 1}-${i}@c.us`, phone: `55119${String(seq * 10 + i).padStart(8, '0')}` }),
    );
    for (const cid of customerIds) addCustomerToList(listId, cid);
    const campaignId = insertCampaign(`Prot Camp ${seq}`, 'x', listId);
    createCampaignRecipients(campaignId, listId);

    const rows = db
      .prepare('SELECT customer_id FROM campaign_recipients WHERE campaign_id = ? ORDER BY customer_id')
      .all(campaignId) as Array<{ customer_id: number }>;
    rows.forEach((row, i) => {
      db.prepare(
        `UPDATE campaign_recipients SET status = ?,
           completed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
         WHERE campaign_id = ? AND customer_id = ?`,
      ).run(statuses[i], campaignId, row.customer_id);
    });
    return campaignId;
  }

  it('6 falhas consecutivas recentes ativam a proteção', () => {
    const campaignId = campaignWithStatuses(['FAILED', 'FAILED', 'FAILED', 'FAILED', 'FAILED', 'FAILED']);
    assert.equal(shouldActivateProtection(campaignId), true);
  });

  it('CANCELLED (não elegíveis) não conta para a taxa de falhas', () => {
    const campaignId = campaignWithStatuses(['SENT', 'CANCELLED', 'CANCELLED', 'CANCELLED', 'CANCELLED', 'CANCELLED']);
    assert.equal(shouldActivateProtection(campaignId), false, '1 SENT + 5 CANCELLED não geram taxa de falha');
  });

  it('PENDING não conta para a taxa de falhas', () => {
    const campaignId = campaignWithStatuses(['FAILED', 'FAILED', 'PENDING', 'PENDING', 'PENDING', 'PENDING']);
    assert.equal(
      shouldActivateProtection(campaignId),
      false,
      '2 FAILED de 2 contados (<5 consecutive e <10 total) não protegem',
    );
  });
});
