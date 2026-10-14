import { Router, type Request, type Response, type NextFunction } from 'express';
import QRCode from 'qrcode';
import { requireAuth } from './auth';
import {
  db,
  addContactToList,
  addCustomerToList,
  cleanOrphanMemberships,
  countContacts,
  countCustomers,
  countListContacts,
  countListCustomers,
  createCampaignRecipients,
  deleteListById,
  getContactById,
  getCampaignById,
  getCampaignRecipients,
  getCampaignResults,
  getCustomerById,
  getCustomerWithContact,
  getListById,
  getListContacts,
  getListCustomers,
  getLists,
  getPreference,
  insertCampaign,
  insertList,
  setOptIn,
  setOptOut,
  listContacts,
  listCustomers,
  listCampaigns,
  promoteContactToCustomer,
  removeContactFromList,
  removeCustomerFromList,
  renameList,
  setCampaignProtection,
  updateCampaignStatus,
  updateCustomerStatus,
} from './db';
import { runDedupe } from './dedupe';
import { seedListsFromRules } from './list-seed';
import { whatsappProvider } from './provider/wwebjs-provider';
import { runSync } from './sync';

export const router = Router();

/**
 * Fluxo único de sincronização: pull do provider -> upsert -> limpeza de
 * memberships órfãs -> dedupe. Nunca cria customers (contato ≠ cliente).
 */
async function syncAndClean(): Promise<Record<string, unknown>> {
  const result = await runSync();
  cleanOrphanMemberships();
  const dedupe = runDedupe();
  return { ...result, dedupe };
}

// ------------------------------------------------------------------
// WhatsApp session
// ------------------------------------------------------------------

router.get('/whatsapp/status', (_req: Request, res: Response) => {
  res.json(whatsappProvider.getStatus());
});

/**
 * QR Code atual da sessão — é o mesmo código exibido pelo
 * web.whatsapp.com oficial (rotaciona a cada ~60s; consulte novamente
 * para obter o código vigente).
 */
router.get('/whatsapp/qr', async (_req: Request, res: Response) => {
  const qr = whatsappProvider.getQr();
  if (!qr || qr.expiresIn <= 0) {
    res.status(404).json({ error: 'Nenhum QR Code válido no momento. Chame POST /api/whatsapp/start e tente novamente.' });
    return;
  }
  try {
    // Renderização em paralelo: PNG (para <img>) e SVG vetorial.
    const [dataUrl, svg] = await Promise.all([
      QRCode.toDataURL(qr.qr, {
        errorCorrectionLevel: 'M',
        margin: 2,
        width: 512,
        color: { dark: '#111b21ff', light: '#ffffffff' },
      }),
      QRCode.toString(qr.qr, {
        type: 'svg',
        errorCorrectionLevel: 'M',
        margin: 2,
        color: { dark: '#111b21', light: '#ffffff' },
      }),
    ]);
    res.json({
      qr: qr.qr,
      dataUrl,
      svg,
      generatedAt: qr.generatedAt,
      expiresAt: qr.expiresAt,
      expiresIn: qr.expiresIn,
    });
  } catch {
    res.status(500).json({ error: 'Falha ao gerar imagem do QR Code.' });
  }
});

router.post('/whatsapp/start', requireAuth, (_req: Request, res: Response) => {
  whatsappProvider.start();
  res.status(202).json({ message: 'Inicialização iniciada.', state: whatsappProvider.getStatus().state });
});

/** Health check leve da sessão com o servidor do WhatsApp. */
router.get('/whatsapp/health', async (_req: Request, res: Response) => {
  const healthy = await whatsappProvider.healthCheck();
  res.status(healthy ? 200 : 503).json({ healthy, ...whatsappProvider.getStatus() });
});

router.post('/whatsapp/logout', requireAuth, async (_req: Request, res: Response) => {
  await whatsappProvider.logout();
  res.json({ message: 'Logout realizado.', state: whatsappProvider.getStatus().state });
});

// ------------------------------------------------------------------
// Contacts
// ------------------------------------------------------------------

router.post('/contacts/sync', requireAuth, async (_req: Request, res: Response) => {
  try {
    res.json(await syncAndClean());
  } catch (err) {
    res.status(409).json({ error: err instanceof Error ? err.message : 'Falha na sincronização.' });
  }
});

/**
 * Remove duplicados sem nova sincronização:
 * contatos @lid e consolidação de nomes repetidos (mantém a linha mais antiga).
 */
router.post('/contacts/dedupe', requireAuth, (_req: Request, res: Response) => {
  res.json({ dedupe: runDedupe() });
});

router.get('/contacts', (req: Request, res: Response) => {
  const limit = Math.min(Math.max(parseInt(String(req.query.limit ?? '50'), 10) || 50, 1), 500);
  const offset = Math.max(parseInt(String(req.query.offset ?? '0'), 10) || 0, 0);
  const parseFlag = (v: unknown): number | undefined => (v === 'true' ? 1 : v === 'false' ? 0 : undefined);
  const filter = {
    limit,
    offset,
    isGroup: parseFlag(req.query.isGroup),
    isBusiness: parseFlag(req.query.isBusiness),
  };
  res.json({ total: countContacts(filter), limit, offset, contacts: listContacts(filter) });
});

router.get('/contacts/:id', (req: Request, res: Response) => {
  const contact = getContactById(Number(req.params.id));
  if (!contact) {
    res.status(404).json({ error: 'Contato não encontrado.' });
    return;
  }
  res.json(contact);
});

// ------------------------------------------------------------------
// Customers
// ------------------------------------------------------------------

router.get('/customers', (req: Request, res: Response) => {
  const limit = Math.min(Math.max(parseInt(String(req.query.limit ?? '50'), 10) || 50, 1), 500);
  const offset = Math.max(parseInt(String(req.query.offset ?? '0'), 10) || 0, 0);
  const customerStatus = typeof req.query.customerStatus === 'string' ? req.query.customerStatus : undefined;
  const filter = { limit, offset, customerStatus };
  res.json({ total: countCustomers({ customerStatus }), limit, offset, customers: listCustomers(filter) });
});

router.get('/customers/:id', (req: Request, res: Response) => {
  const customer = getCustomerWithContact(Number(req.params.id));
  if (!customer) {
    res.status(404).json({ error: 'Cliente não encontrado.' });
    return;
  }
  res.json(customer);
});

/** Promote a contact to customer (idempotent). */
router.post('/customers/:contactId/promote', requireAuth, (req: Request, res: Response) => {
  const contactId = Number(req.params.contactId);
  const contact = getContactById(contactId);
  if (!contact) {
    res.status(404).json({ error: 'Contato não encontrado.' });
    return;
  }
  const status = typeof req.body?.status === 'string' ? req.body.status : 'UNKNOWN';
  if (!['CUSTOMER', 'PROSPECT', 'UNKNOWN'].includes(status)) {
    res.status(400).json({ error: 'Status inválido. Use: CUSTOMER, PROSPECT, UNKNOWN.' });
    return;
  }
  const id = promoteContactToCustomer(contactId, status);
  res.status(201).json(getCustomerById(id));
});

router.put('/customers/:id/status', requireAuth, (req: Request, res: Response) => {
  const id = Number(req.params.id);
  const customer = getCustomerById(id);
  if (!customer) {
    res.status(404).json({ error: 'Cliente não encontrado.' });
    return;
  }
  const status = typeof req.body?.status === 'string' ? req.body.status : '';
  if (!['CUSTOMER', 'PROSPECT', 'UNKNOWN'].includes(status)) {
    res.status(400).json({ error: 'Status inválido. Use: CUSTOMER, PROSPECT, UNKNOWN.' });
    return;
  }
  updateCustomerStatus(id, status);
  res.json(getCustomerById(id));
});

/**
 * Mesmo fluxo de POST /contacts/sync (compatibilidade histórica).
 * Observação: NÃO promove contatos a customers — contato ≠ cliente.
 * A promoção é explícita via POST /customers/:contactId/promote.
 */
router.post('/customers/sync', requireAuth, async (_req: Request, res: Response) => {
  try {
    res.json(await syncAndClean());
  } catch (err) {
    res.status(409).json({ error: err instanceof Error ? err.message : 'Falha na sincronização.' });
  }
});

// ------------------------------------------------------------------
// Preferences (opt-in / opt-out)
// ------------------------------------------------------------------

router.post('/customers/:id/opt-in', requireAuth, (req: Request, res: Response) => {
  const id = Number(req.params.id);
  const customer = getCustomerById(id);
  if (!customer) {
    res.status(404).json({ error: 'Cliente não encontrado.' });
    return;
  }
  const source = typeof req.body?.source === 'string' ? req.body.source : 'manual';
  setOptIn(id, source);
  res.json({ customerId: id, marketingStatus: 'OPTED_IN', source });
});

router.post('/customers/:id/opt-out', requireAuth, (req: Request, res: Response) => {
  const id = Number(req.params.id);
  const customer = getCustomerById(id);
  if (!customer) {
    res.status(404).json({ error: 'Cliente não encontrado.' });
    return;
  }
  const source = typeof req.body?.source === 'string' ? req.body.source : 'manual';
  setOptOut(id, source);
  res.json({ customerId: id, marketingStatus: 'OPTED_OUT', source });
});

// ------------------------------------------------------------------
// Lists (kept for backward compat, but customer-based)
// ------------------------------------------------------------------

/**
 * Popula automaticamente as listas de transmissão com base em regras
 * de palavras-chave nos nomes dos contatos. Idempotente.
 */
router.post('/lists/seed', requireAuth, (_req: Request, res: Response) => {
  res.json({ results: seedListsFromRules() });
});

router.get('/lists', (_req: Request, res: Response) => {
  const lists = getLists().map((list) => ({
    ...list,
    contactCount: countListContacts(list.id),
    customerCount: countListCustomers(list.id),
  }));
  res.json({ total: lists.length, lists });
});

router.post('/lists', requireAuth, (req: Request, res: Response) => {
  const name = typeof req.body?.name === 'string' ? req.body.name.trim() : '';
  const description = typeof req.body?.description === 'string' ? req.body.description.trim() || null : null;
  if (!name) {
    res.status(400).json({ error: "Campo 'name' é obrigatório." });
    return;
  }
  try {
    const id = insertList(name, description);
    res.status(201).json(getListById(id));
  } catch (err: unknown) {
    if (String(err).includes('UNIQUE')) {
      res.status(409).json({ error: 'Já existe uma lista com esse nome.' });
      return;
    }
    throw err;
  }
});

router.get('/lists/:id', (req: Request, res: Response) => {
  const list = getListById(Number(req.params.id));
  if (!list) {
    res.status(404).json({ error: 'Lista não encontrada.' });
    return;
  }
  res.json({
    ...list,
    contactCount: countListContacts(list.id),
    customerCount: countListCustomers(list.id),
  });
});

router.put('/lists/:id', requireAuth, (req: Request, res: Response) => {
  const id = Number(req.params.id);
  if (!getListById(id)) {
    res.status(404).json({ error: 'Lista não encontrada.' });
    return;
  }
  const name = typeof req.body?.name === 'string' && req.body.name.trim() ? req.body.name.trim() : null;
  const description = typeof req.body?.description === 'string' ? req.body.description.trim() || null : null;
  try {
    renameList(id, name, description);
    res.json(getListById(id));
  } catch (err: unknown) {
    if (String(err).includes('UNIQUE')) {
      res.status(409).json({ error: 'Já existe uma lista com esse nome.' });
      return;
    }
    throw err;
  }
});

router.delete('/lists/:id', requireAuth, (req: Request, res: Response) => {
  if (!deleteListById(Number(req.params.id))) {
    res.status(404).json({ error: 'Lista não encontrada.' });
    return;
  }
  res.status(204).send();
});

// ---- List contacts (legacy, backward compat) ----

router.get('/lists/:id/contacts', (req: Request, res: Response) => {
  const id = Number(req.params.id);
  if (!getListById(id)) {
    res.status(404).json({ error: 'Lista não encontrada.' });
    return;
  }
  res.json({ total: countListContacts(id), contacts: getListContacts(id) });
});

router.post('/lists/:id/contacts/:contactId', requireAuth, (req: Request, res: Response) => {
  const listId = Number(req.params.id);
  const contactId = Number(req.params.contactId);
  if (!getListById(listId)) {
    res.status(404).json({ error: 'Lista não encontrada.' });
    return;
  }
  if (!getContactById(contactId)) {
    res.status(404).json({ error: 'Contato não encontrado.' });
    return;
  }
  // INSERT OR IGNORE -> idempotent
  addContactToList(listId, contactId);
  res.status(201).json({ listId, contactId });
});

router.delete('/lists/:id/contacts/:contactId', requireAuth, (req: Request, res: Response) => {
  const listId = Number(req.params.id);
  const contactId = Number(req.params.contactId);
  if (!removeContactFromList(listId, contactId)) {
    res.status(404).json({ error: 'Contato não está nessa lista.' });
    return;
  }
  res.status(204).send();
});

// ---- List customers (new, customer-based) ----

router.get('/lists/:id/customers', (req: Request, res: Response) => {
  const id = Number(req.params.id);
  if (!getListById(id)) {
    res.status(404).json({ error: 'Lista não encontrada.' });
    return;
  }
  res.json({ total: countListCustomers(id), customers: getListCustomers(id) });
});

router.post('/lists/:id/customers/:customerId', requireAuth, (req: Request, res: Response) => {
  const listId = Number(req.params.id);
  const customerId = Number(req.params.customerId);
  if (!getListById(listId)) {
    res.status(404).json({ error: 'Lista não encontrada.' });
    return;
  }
  if (!getCustomerById(customerId)) {
    res.status(404).json({ error: 'Cliente não encontrado.' });
    return;
  }
  addCustomerToList(listId, customerId);
  res.status(201).json({ listId, customerId });
});

router.delete('/lists/:id/customers/:customerId', requireAuth, (req: Request, res: Response) => {
  const listId = Number(req.params.id);
  const customerId = Number(req.params.customerId);
  if (!removeCustomerFromList(listId, customerId)) {
    res.status(404).json({ error: 'Cliente não está nessa lista.' });
    return;
  }
  res.status(204).send();
});

/**
 * Re-synchronizes contacts and recalculates list memberships
 * (removes memberships whose contact/list disappeared). Idempotent.
 */
router.post('/lists/:id/sync', requireAuth, async (req: Request, res: Response) => {
  const id = Number(req.params.id);
  if (!getListById(id)) {
    res.status(404).json({ error: 'Lista não encontrada.' });
    return;
  }
  try {
    const sync = await runSync();
    cleanOrphanMemberships();
    res.json({ sync, listId: id, contactCount: countListContacts(id), customerCount: countListCustomers(id) });
  } catch (err) {
    res.status(409).json({ error: err instanceof Error ? err.message : 'Falha na sincronização.' });
  }
});

// ------------------------------------------------------------------
// Campaigns
// ------------------------------------------------------------------

router.get('/campaigns', (_req: Request, res: Response) => {
  const campaigns = listCampaigns();
  res.json({ total: campaigns.length, campaigns });
});

router.post('/campaigns', requireAuth, (req: Request, res: Response) => {
  const name = typeof req.body?.name === 'string' ? req.body.name.trim() : '';
  const message = typeof req.body?.message === 'string' ? req.body.message.trim() : '';
  const listId = Number(req.body?.listId);

  if (!name) {
    res.status(400).json({ error: "Campo 'name' é obrigatório." });
    return;
  }
  if (!message) {
    res.status(400).json({ error: "Campo 'message' é obrigatório." });
    return;
  }
  if (!listId || !getListById(listId)) {
    res.status(400).json({ error: "Campo 'listId' é obrigatório e deve referenciar uma lista existente." });
    return;
  }

  const id = insertCampaign(name, message, listId);
  res.status(201).json(getCampaignById(id));
});

router.get('/campaigns/:id', (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) {
    res.status(404).json({ error: 'Campanha não encontrada.' });
    return;
  }
  res.json(campaign);
});

/** Preview: calculates eligible recipients without sending anything. */
router.post('/campaigns/:id/preview', requireAuth, (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) {
    res.status(404).json({ error: 'Campanha não encontrada.' });
    return;
  }
  if (campaign.status !== 'DRAFT') {
    res.status(409).json({ error: 'Preview só disponível para campanhas em DRAFT.' });
    return;
  }

  const preview = createCampaignRecipients(campaign.id, campaign.list_id);
  res.json({
    campaignId: campaign.id,
    name: campaign.name,
    listId: campaign.list_id,
    selected: preview.total,
    eligible: preview.eligible,
    optedOut: preview.optedOut,
    blocked: preview.blocked,
    duplicates: preview.duplicates,
    message: campaign.message,
  });
});

/** Start: begins processing the campaign queue. */
router.post('/campaigns/:id/start', requireAuth, (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) {
    res.status(404).json({ error: 'Campanha não encontrada.' });
    return;
  }
  if (campaign.status !== 'DRAFT' && campaign.status !== 'PAUSED') {
    res.status(409).json({ error: `Não é possível iniciar campanha com status ${campaign.status}.` });
    return;
  }

  // If DRAFT, create recipients first
  if (campaign.status === 'DRAFT') {
    createCampaignRecipients(campaign.id, campaign.list_id);
  }

  updateCampaignStatus(campaign.id, 'RUNNING');
  res.json({ message: 'Campanha iniciada.', campaign: getCampaignById(campaign.id) });
});

/** Pause: stops processing but keeps state. */
router.post('/campaigns/:id/pause', requireAuth, (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) {
    res.status(404).json({ error: 'Campanha não encontrada.' });
    return;
  }
  if (campaign.status !== 'RUNNING') {
    res.status(409).json({ error: `Não é possível pausar campanha com status ${campaign.status}.` });
    return;
  }

  updateCampaignStatus(campaign.id, 'PAUSED');
  res.json({ message: 'Campanha pausada.', campaign: getCampaignById(campaign.id) });
});

/** Cancel: stops processing and marks all pending as cancelled. */
router.post('/campaigns/:id/cancel', requireAuth, (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) {
    res.status(404).json({ error: 'Campanha não encontrada.' });
    return;
  }
  if (campaign.status === 'COMPLETED' || campaign.status === 'CANCELLED') {
    res.status(409).json({ error: `Campanha já está ${campaign.status}.` });
    return;
  }

  // Cancel all pending/processing recipients
  db.prepare(
    `UPDATE campaign_recipients SET status = 'CANCELLED' WHERE campaign_id = ? AND status IN ('PENDING', 'PROCESSING')`,
  ).run(campaign.id);

  updateCampaignStatus(campaign.id, 'CANCELLED');
  res.json({ message: 'Campanha cancelada.', campaign: getCampaignById(campaign.id) });
});

router.get('/campaigns/:id/recipients', (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) {
    res.status(404).json({ error: 'Campanha não encontrada.' });
    return;
  }
  const recipients = getCampaignRecipients(campaign.id);
  res.json({ total: recipients.length, recipients });
});

router.get('/campaigns/:id/results', (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) {
    res.status(404).json({ error: 'Campanha não encontrada.' });
    return;
  }
  res.json({ campaign: getCampaignById(campaign.id), results: getCampaignResults(campaign.id) });
});
