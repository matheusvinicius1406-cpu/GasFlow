/**
 * Testes do worker de broadcast: drenagem de não elegíveis (CANCELLED),
 * release de claim quando o provider está offline, política de proteção e
 * fluxo de envio com provider mockado. O timer do worker NUNCA é iniciado —
 * processNext() é chamado manualmente.
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
  setOptOut,
  insertCampaign,
  createCampaignRecipients,
  getCampaignById,
  getCampaignResults,
  updateCampaignStatus,
} = require('../src/db');

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { processNext, shouldActivateProtection } = require('../src/broadcast');

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { whatsappProvider } = require('../src/provider/wwebjs-provider');

type ProviderPatch = {
  isConnected: () => boolean;
  sendMessage: (recipient: string, message: { text: string }) => Promise<{ success: boolean; messageId?: string; error?: string }>;
};

const provider = whatsappProvider as ProviderPatch;
const originalIsConnected = provider.isConnected;
const originalSendMessage = provider.sendMessage;

after(() => {
  provider.isConnected = originalIsConnected;
  provider.sendMessage = originalSendMessage;
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

let seq = 0;

function makeContact(opts: { phone: string | null; jid: string; name?: string | null }): number {
  seq += 1;
  insertContact({
    phone: opts.phone,
    jid: opts.jid,
    name: opts.name ?? `Contact ${seq}`,
    pushName: null,
    businessName: null,
    isBusiness: 0,
    isGroup: 0,
  });
  const row = db.prepare('SELECT id FROM contacts WHERE jid = ?').get(opts.jid) as { id: number };
  return row.id;
}

function makeCustomer(opts: { phone: string | null; jid: string }): number {
  const contactId = makeContact(opts);
  return promoteContactToCustomer(contactId, 'CUSTOMER');
}

function setupCampaign(customerIds: number[]): number {
  seq += 1;
  const listId = insertList(`BW Lista ${seq}`, null);
  for (const cid of customerIds) addCustomerToList(listId, cid);
  const campaignId = insertCampaign(`BW Camp ${seq}`, 'Mensagem de teste', listId);
  createCampaignRecipients(campaignId, listId);
  return campaignId;
}

// ---------------------------------------------------------------------------

test('offline: drena não elegíveis e devolve o claim do elegível sem queimar retry', async () => {
  // Ordem importa: claim ordena por customer_id.
  const noPhone = makeCustomer({ phone: null, jid: `bw-nophone-${seq + 1}@lid` });
  const optedOut = makeCustomer({ phone: '5511940000001', jid: `bw-optout-${seq + 1}@c.us` });
  const eligible = makeCustomer({ phone: '5511940000002', jid: `bw-eligible-${seq + 1}@c.us` });

  const campaignId = setupCampaign([noPhone, optedOut, eligible]);

  // Opt-out APLICADO DEPOIS da criação dos recipients (caminho do worker).
  setOptOut(optedOut, 'test');
  updateCampaignStatus(campaignId, 'RUNNING');

  // Provider desconectado (estado padrão antes do start()).
  assert.equal(provider.isConnected(), false);
  await processNext();

  const results = getCampaignResults(campaignId);
  assert.equal(results.cancelled, 2, 'não elegíveis viram CANCELLED');
  assert.equal(results.failed, 0, 'CANCELLED não conta como falha de envio');
  assert.equal(results.pending, 1, 'elegível segue PENDING (claim devolvido)');
  assert.equal(results.processing, 0, 'nada fica preso em PROCESSING');

  const pending = db
    .prepare(
      "SELECT customer_id, attempts FROM campaign_recipients WHERE campaign_id = ? AND status = 'PENDING'",
    )
    .all(campaignId) as Array<{ customer_id: number; attempts: number }>;
  assert.equal(pending.length, 1);
  assert.equal(pending[0].customer_id, eligible);
  assert.equal(pending[0].attempts, 0, 'release desfaz o incremento de attempts');

  assert.equal(getCampaignById(campaignId)?.status, 'RUNNING', 'campanha não completa com pendente remanescente');

  // Encerra aqui para não interferir nos próximos testes (fila é global).
  updateCampaignStatus(campaignId, 'CANCELLED');
});

test('offline: campanha 100% não elegível é COMPLETED mesmo sem provider', async () => {
  const noPhone = makeCustomer({ phone: null, jid: `bw-only-nophone-${seq + 1}@lid` });
  const campaignId = setupCampaign([noPhone]);
  updateCampaignStatus(campaignId, 'RUNNING');

  await processNext();

  const results = getCampaignResults(campaignId);
  assert.equal(results.cancelled, 1);
  assert.equal(results.pending, 0);
  assert.equal(getCampaignById(campaignId)?.status, 'COMPLETED');
});

test('proteção: 6 falhas consecutivas recentes ativam a proteção', () => {
  const campaignId = setupCampaign(
    Array.from({ length: 6 }, () => makeCustomer({ phone: '5511950000001', jid: `bw-prot-a-${seq + 1}@c.us` })),
  );
  db.prepare(
    `UPDATE campaign_recipients SET status = 'FAILED',
       completed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE campaign_id = ?`,
  ).run(campaignId);

  assert.equal(shouldActivateProtection(campaignId), true);
});

test('proteção: taxa pequena de falhas NÃO ativa a proteção', () => {
  const campaignId = setupCampaign(
    Array.from({ length: 4 }, () => makeCustomer({ phone: '5511950000002', jid: `bw-prot-b-${seq + 1}@c.us` })),
  );
  const rows = db
    .prepare('SELECT customer_id FROM campaign_recipients WHERE campaign_id = ? ORDER BY customer_id')
    .all(campaignId) as Array<{ customer_id: number }>;
  rows.forEach((r, i) => {
    db.prepare(
      `UPDATE campaign_recipients SET status = ?, completed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
       WHERE campaign_id = ? AND customer_id = ?`,
    ).run(i < 2 ? 'FAILED' : 'SENT', campaignId, r.customer_id);
  });

  assert.equal(shouldActivateProtection(campaignId), false, '2/4 falhas e <5 consecutive não protegem');
});

test('proteção: CANCELLED (não elegíveis) não contam para a taxa de falhas', () => {
  const campaignId = setupCampaign(
    Array.from({ length: 13 }, () => makeCustomer({ phone: '5511950000003', jid: `bw-prot-c-${seq + 1}@c.us` })),
  );
  const rows = db
    .prepare('SELECT customer_id FROM campaign_recipients WHERE campaign_id = ? ORDER BY customer_id')
    .all(campaignId) as Array<{ customer_id: number }>;
  rows.forEach((r, i) => {
    db.prepare('UPDATE campaign_recipients SET status = ? WHERE campaign_id = ? AND customer_id = ?').run(
      i === 0 ? 'SENT' : 'CANCELLED',
      campaignId,
      r.customer_id,
    );
  });

  assert.equal(shouldActivateProtection(campaignId), false, '12 CANCELLED não geram taxa de falha');
});

test('envio com provider mockado marca SENT e conclui a campanha', async () => {
  const first = makeCustomer({ phone: '5511960000001', jid: `bw-send-1-${seq + 1}@c.us` });
  const second = makeCustomer({ phone: '5511960000002', jid: `bw-send-2-${seq + 1}@c.us` });
  const campaignId = setupCampaign([first, second]);
  updateCampaignStatus(campaignId, 'RUNNING');

  const sentTo: string[] = [];
  provider.isConnected = () => true;
  provider.sendMessage = async (recipient: string) => {
    sentTo.push(recipient);
    return { success: true, messageId: `msg-${sentTo.length}` };
  };

  await processNext(); // envia 1 e respeita o cooldown entre ciclos
  let results = getCampaignResults(campaignId);
  assert.equal(results.sent, 1, 'um envio por ciclo');
  assert.equal(results.pending, 1);

  await processNext(); // envia 2
  await processNext(); // fila vazia -> COMPLETED

  results = getCampaignResults(campaignId);
  assert.equal(results.sent, 2);
  assert.equal(results.failed, 0);
  assert.equal(getCampaignById(campaignId)?.status, 'COMPLETED');
  assert.deepEqual(sentTo.sort(), ['5511960000001', '5511960000002']);

  const providerIds = db
    .prepare("SELECT provider_message_id FROM campaign_recipients WHERE campaign_id = ? AND status = 'SENT'")
    .all(campaignId) as Array<{ provider_message_id: string }>;
  assert.deepEqual(providerIds.map((r) => r.provider_message_id).sort(), ['msg-1', 'msg-2']);

  provider.isConnected = originalIsConnected;
  provider.sendMessage = originalSendMessage;
});

test('falha de envio conta como FAILED e não zera a campanha', async () => {
  const only = makeCustomer({ phone: '5511970000001', jid: `bw-fail-${seq + 1}@c.us` });
  const campaignId = setupCampaign([only]);
  updateCampaignStatus(campaignId, 'RUNNING');

  provider.isConnected = () => true;
  provider.sendMessage = async () => ({ success: false, error: 'Número inválido' });

  await processNext();

  const results = getCampaignResults(campaignId);
  assert.equal(results.failed, 1);
  assert.equal(results.sent, 0);
  const row = db
    .prepare("SELECT last_error FROM campaign_recipients WHERE campaign_id = ? AND status = 'FAILED'")
    .get(campaignId) as { last_error: string };
  assert.match(String(row.last_error), /inválido/);

  provider.isConnected = originalIsConnected;
  provider.sendMessage = originalSendMessage;
});
