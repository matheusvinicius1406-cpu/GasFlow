import { Router, type Request, type Response } from 'express';
import path from 'node:path';
import { existsSync } from 'node:fs';
import QRCode from 'qrcode';
import { requireAuth } from './auth';
import { providerManager } from './provider/provider-manager';
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
  updateCampaignStatus,
  updateCustomerStatus,
} from './db';
import { runDedupe } from './dedupe';
import { seedListsFromRules } from './list-seed';
import { runSync } from './sync';
import { checkRate, recordSend } from './anti-ban';
import { logger } from './log';

export const router = Router();

// ═══════════════════════════════════════════════════════════
// WhatsApp Multi-Account
// ═══════════════════════════════════════════════════════════

/** List all WhatsApp accounts with status */
// GETs de dados protegidos: sem auth, QR/contatos/campanhas ficam expostos
// na rede (QR escaneado por terceiro = sequestro da sessão do bot).
router.get('/whatsapp/accounts', requireAuth, (_req: Request, res: Response) => {
  const accounts = providerManager.getAllAccounts();
  res.json({ accounts, total: accounts.length });
});

/** Get single account status */
router.get('/whatsapp/accounts/:id', requireAuth, (req: Request, res: Response) => {
  const account = providerManager.getAccount(req.params.id);
  if (!account) {
    res.status(404).json({ error: 'Conta não encontrada.' });
    return;
  }
  res.json(account.getAccountStatus());
});

/** Start a specific account */
router.post('/whatsapp/accounts/:id/start', requireAuth, (req: Request, res: Response) => {
  try {
    providerManager.startAccount(req.params.id);
    const account = providerManager.getAccount(req.params.id);
    res.status(202).json({ message: 'Inicialização iniciada.', status: account?.getStatus() });
  } catch (err) {
    res.status(404).json({ error: err instanceof Error ? err.message : 'Erro ao iniciar conta.' });
  }
});

/** Stop a specific account */
router.post('/whatsapp/accounts/:id/stop', requireAuth, async (req: Request, res: Response) => {
  try {
    await providerManager.stopAccount(req.params.id);
    res.json({ message: 'Conta parada.' });
  } catch (err) {
    res.status(404).json({ error: err instanceof Error ? err.message : 'Erro ao parar conta.' });
  }
});

/** Logout a specific account */
router.post('/whatsapp/accounts/:id/logout', requireAuth, async (req: Request, res: Response) => {
  try {
    await providerManager.logoutAccount(req.params.id);
    res.json({ message: 'Logout realizado.' });
  } catch (err) {
    res.status(404).json({ error: err instanceof Error ? err.message : 'Erro ao fazer logout.' });
  }
});

/** Get QR code for a specific account */
router.get('/whatsapp/accounts/:id/qr', requireAuth, async (req: Request, res: Response) => {
  const account = providerManager.getAccount(req.params.id);
  if (!account) {
    res.status(404).json({ error: 'Conta não encontrada.' });
    return;
  }
  const qr = account.getQr();
  if (!qr || qr.expiresIn <= 0) {
    res.status(404).json({ error: 'Nenhum QR Code válido. Inicie a sessão primeiro.' });
    return;
  }
  try {
    const [dataUrl, svg] = await Promise.all([
      QRCode.toDataURL(qr.qr, {
        errorCorrectionLevel: 'M', margin: 2, width: 512,
        color: { dark: '#111b21ff', light: '#ffffffff' },
      }),
      QRCode.toString(qr.qr, {
        type: 'svg', errorCorrectionLevel: 'M', margin: 2,
        color: { dark: '#111b21', light: '#ffffff' },
      }),
    ]);
    res.json({ qr: qr.qr, dataUrl, svg, generatedAt: qr.generatedAt, expiresAt: qr.expiresAt, expiresIn: qr.expiresIn });
  } catch {
    res.status(500).json({ error: 'Falha ao gerar imagem do QR Code.' });
  }
});

/** Health check for a specific account */
router.get('/whatsapp/accounts/:id/health', async (req: Request, res: Response) => {
  const account = providerManager.getAccount(req.params.id);
  if (!account) {
    res.status(404).json({ error: 'Conta não encontrada.' });
    return;
  }
  const healthy = await account.healthCheck();
  res.status(healthy ? 200 : 503).json({ healthy, ...account.getStatus() });
});


// ═══════════════════════════════════════════════════════════
// FASE 5: Message Sending with Idempotency
// ═══════════════════════════════════════════════════════════

import { normalizePhone } from './normalize';
import { insertSentMessage, markSentMessageSent, markSentMessageFailed, findSentMessageByKey, listSentMessages } from './db';

const MAX_MESSAGE_LENGTH = 4096;

/** Standard error codes for the messaging API */
export type MessageErrorCode =
  | 'ACCOUNT_NOT_FOUND'
  | 'ACCOUNT_NOT_CONNECTED'
  | 'INVALID_PHONE'
  | 'EMPTY_MESSAGE'
  | 'MESSAGE_TOO_LONG'
  | 'MESSAGE_SEND_FAILED'
  | 'DUPLICATE_IDEMPOTENCY_KEY'
  | 'SERVICE_UNAVAILABLE';

/**
 * POST /api/whatsapp/accounts/:id/messages
 *
 * Send a message via a specific WhatsApp account.
 * Supports idempotency via idempotency_key.
 */
router.post('/whatsapp/accounts/:id/messages', requireAuth, async (req: Request, res: Response) => {
  const accountId = req.params.id;
  const { recipient, message, idempotency_key } = req.body ?? {};

  // 1. Validate account exists
  const account = providerManager.getAccount(accountId);
  if (!account) {
    res.status(404).json({ error: 'ACCOUNT_NOT_FOUND', detail: 'Conta não encontrada.' });
    return;
  }

  // 2. Validate account is connected
  if (!account.isConnected()) {
    res.status(409).json({ error: 'ACCOUNT_NOT_CONNECTED', detail: 'Conta não está conectada.' });
    return;
  }

  // 3. Validate recipient (phone)
  const normalizedPhone = normalizePhone(recipient);
  if (!normalizedPhone) {
    res.status(400).json({ error: 'INVALID_PHONE', detail: 'Número de telefone inválido.' });
    return;
  }

  // 4. Validate message
  if (!message || typeof message !== 'string' || message.trim().length === 0) {
    res.status(400).json({ error: 'EMPTY_MESSAGE', detail: 'Mensagem não pode ser vazia.' });
    return;
  }
  if (message.length > MAX_MESSAGE_LENGTH) {
    res.status(400).json({ error: 'MESSAGE_TOO_LONG', detail: `Mensagem excede ${MAX_MESSAGE_LENGTH} caracteres.` });
    return;
  }

  // 5. Idempotency
  const idempotencyKey = idempotency_key || `${accountId}:${normalizedPhone}:${Date.now()}`;
  const existing = findSentMessageByKey(idempotencyKey);
  if (existing && existing.status === 'SENT') {
    // Already sent — return success without re-sending
    res.json({
      success: true,
      messageId: existing.provider_msg_id,
      idempotencyKey: existing.idempotency_key,
      duplicate: true,
    });
    return;
  }
  if (existing && existing.status === 'PENDING') {
    // Currently being processed — return conflict
    res.status(409).json({ error: 'DUPLICATE_IDEMPOTENCY_KEY', detail: 'Mensagem já está sendo processada.' });
    return;
  }

  // 6. Anti-ban: conversacional também respeita caps/cooldown (antes só o
  // broadcast passava pelos gates — automações e API podiam rajadas).
  const rate = checkRate(accountId, normalizedPhone);
  if (!rate.allowed) {
    const retryAfterSec = rate.retryAtMs ? Math.max(1, Math.ceil((rate.retryAtMs - Date.now()) / 1000)) : 60;
    res.set('Retry-After', String(retryAfterSec));
    res.status(429).json({
      error: 'RATE_LIMITED',
      detail: `Envio bloqueado pelo anti-ban (${rate.reason}). Tente em ${retryAfterSec}s.`,
    });
    return;
  }

  // 7. Insert record (PENDING)
  const record = insertSentMessage({
    idempotencyKey,
    accountId,
    recipient: normalizedPhone,
    messageText: message.trim(),
  });

  // 8. Send via provider
  try {
    const result = await account.sendMessage(normalizedPhone, { text: message.trim() });

    if (result.success) {
      markSentMessageSent(record.id, result.messageId || 'unknown');
      recordSend(accountId, normalizedPhone, result.messageId);
      logger.info('message.sent', { phone: normalizedPhone, accountId, idempotencyKey });
      res.json({
        success: true,
        messageId: result.messageId,
        idempotencyKey,
      });
    } else {
      markSentMessageFailed(record.id, result.error || 'Unknown error');
      logger.warn('message.failed', { phone: normalizedPhone, accountId, error: result.error });
      res.status(500).json({
        error: 'MESSAGE_SEND_FAILED',
        detail: result.error || 'Falha ao enviar mensagem.',
      });
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : 'Unknown error';
    markSentMessageFailed(record.id, errorMsg);
    logger.error('message.error', { phone: normalizedPhone, accountId, error: errorMsg });
    res.status(500).json({
      error: 'SERVICE_UNAVAILABLE',
      detail: 'Serviço de mensageria temporariamente indisponível.',
    });
  }
});

/**
 * GET /api/whatsapp/accounts/:id/messages
 *
 * List sent messages for an account.
 */
router.get('/whatsapp/accounts/:id/messages', requireAuth, (req: Request, res: Response) => {
  const accountId = req.params.id;
  const account = providerManager.getAccount(accountId);
  if (!account) {
    res.status(404).json({ error: 'ACCOUNT_NOT_FOUND', detail: 'Conta não encontrada.' });
    return;
  }
  const limit = Math.min(Math.max(parseInt(String(req.query.limit ?? '50'), 10) || 50, 1), 200);
  const offset = Math.max(parseInt(String(req.query.offset ?? '0'), 10) || 0, 0);
  const messages = listSentMessages(accountId, limit, offset);
  res.json({ messages, total: messages.length, limit, offset });
});

const MAX_MEDIA_BASE64_LENGTH = 25 * 1024 * 1024; // 25MB em base64 (~18MB binário)

/**
 * Diretório allowlist para mediaPath — segurança: sem isso a rota leria
 * ARQUIVO ARBITRÁRIO do servidor (ex.: ../../.env) e o exfiltraria como
 * anexo de WhatsApp. Config via WA_UPLOADS_DIR; default <cwd>/uploads.
 */
const ALLOWED_MEDIA_DIR = path.resolve(
  process.env.WA_UPLOADS_DIR || path.join(process.cwd(), 'uploads'),
);

function resolveSafeMediaPath(raw: string): string | null {
  const resolved = path.resolve(String(raw));
  // Prefixo + separador evita bypass tipo /uploads-evil (fora de /uploads).
  if (resolved !== ALLOWED_MEDIA_DIR && !resolved.startsWith(ALLOWED_MEDIA_DIR + path.sep)) {
    return null;
  }
  if (!existsSync(resolved)) return null;
  return resolved;
}

/**
 * POST /api/whatsapp/accounts/:id/media
 *
 * Envia mídia (imagem, áudio, documento) via uma conta específica.
 * Aceita `data` (base64) + `mimetype`, ou `mediaPath` (arquivo no servidor).
 * Suporta idempotência via idempotency_key (mesma semântica de /messages).
 */
router.post('/whatsapp/accounts/:id/media', requireAuth, async (req: Request, res: Response) => {
  const accountId = req.params.id;
  const { recipient, caption, data, mimetype, filename, mediaPath, idempotency_key } = req.body ?? {};

  // 1. Validate account exists and is connected
  const account = providerManager.getAccount(accountId);
  if (!account) {
    res.status(404).json({ error: 'ACCOUNT_NOT_FOUND', detail: 'Conta não encontrada.' });
    return;
  }
  if (!account.isConnected()) {
    res.status(409).json({ error: 'ACCOUNT_NOT_CONNECTED', detail: 'Conta não está conectada.' });
    return;
  }

  // 2. Validate recipient
  const normalizedPhone = normalizePhone(recipient);
  if (!normalizedPhone) {
    res.status(400).json({ error: 'INVALID_PHONE', detail: 'Número de telefone inválido.' });
    return;
  }

  // 3. Resolve mídia: data+mimetype (base64) OU mediaPath (arquivo no servidor)
  let mediaData = data;
  let mediaMime = mimetype;
  if (mediaPath) {
    const safePath = resolveSafeMediaPath(String(mediaPath));
    if (!safePath) {
      res.status(400).json({
        error: 'MEDIA_PATH_INVALID',
        detail: `mediaPath deve estar dentro de ${ALLOWED_MEDIA_DIR} e existir.`,
      });
      return;
    }
    try {
      const { readFileSync } = await import('node:fs');
      const buffer = readFileSync(safePath);
      mediaData = buffer.toString('base64');
      mediaMime = mediaMime || 'application/octet-stream';
    } catch {
      res.status(400).json({ error: 'MEDIA_PATH_INVALID', detail: 'Não foi possível ler mediaPath.' });
      return;
    }
  }
  if (!mediaData || typeof mediaData !== 'string' || !mediaMime || typeof mediaMime !== 'string') {
    res.status(400).json({ error: 'MEDIA_INVALID', detail: 'Forneça data (base64) + mimetype, ou mediaPath.' });
    return;
  }
  if (mediaData.length > MAX_MEDIA_BASE64_LENGTH) {
    res.status(400).json({ error: 'MEDIA_TOO_LARGE', detail: `Mídia excede o limite de ${MAX_MEDIA_BASE64_LENGTH / 1024 / 1024}MB.` });
    return;
  }

  // 4. Idempotency
  const idempotencyKey = idempotency_key || `${accountId}:media:${normalizedPhone}:${Date.now()}`;
  const existing = findSentMessageByKey(idempotencyKey);
  if (existing && existing.status === 'SENT') {
    res.json({ success: true, messageId: existing.provider_msg_id, idempotencyKey, duplicate: true });
    return;
  }
  if (existing && existing.status === 'PENDING') {
    res.status(409).json({ error: 'DUPLICATE_IDEMPOTENCY_KEY', detail: 'Mensagem já está sendo processada.' });
    return;
  }

  // 5. Insert record (PENDING)
  const record = insertSentMessage({
    idempotencyKey,
    accountId,
    recipient: normalizedPhone,
    messageText: caption ? String(caption).slice(0, 4096) : `[media:${mediaMime}]`,
  });

  // 6. Send via provider
  try {
    const result = await account.sendMedia(normalizedPhone, {
      data: mediaData as string,
      mimetype: mediaMime as string,
      filename: filename ? String(filename) : undefined,
      caption: caption ? String(caption) : undefined,
    });
    if (result.success) {
      markSentMessageSent(record.id, result.messageId || 'unknown');
      logger.info('media.sent', { phone: normalizedPhone, accountId, idempotencyKey });
      res.json({ success: true, messageId: result.messageId, idempotencyKey });
    } else {
      markSentMessageFailed(record.id, result.error || 'Unknown error');
      res.status(500).json({ error: 'MEDIA_SEND_FAILED', detail: result.error || 'Falha ao enviar mídia.' });
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : 'Unknown error';
    markSentMessageFailed(record.id, errorMsg);
    res.status(500).json({ error: 'SERVICE_UNAVAILABLE', detail: 'Serviço de mensageria temporariamente indisponível.' });
  }
});
// ── Legacy endpoints (backward compat) ──────────────────

router.get('/whatsapp/status', requireAuth, (_req: Request, res: Response) => {
  const accounts = providerManager.getAllAccounts();
  res.json({ accounts, primary: accounts[0] });
});

router.get('/whatsapp/qr', requireAuth, async (_req: Request, res: Response) => {
  const account = providerManager.getAccount('primary');
  if (!account) {
    res.status(404).json({ error: 'Conta principal não encontrada.' });
    return;
  }
  const qr = account.getQr();
  if (!qr || qr.expiresIn <= 0) {
    res.status(404).json({ error: 'Nenhum QR Code válido.' });
    return;
  }
  try {
    const dataUrl = await QRCode.toDataURL(qr.qr, { errorCorrectionLevel: 'M', margin: 2, width: 512 });
    res.json({ qr: qr.qr, dataUrl, generatedAt: qr.generatedAt, expiresAt: qr.expiresAt, expiresIn: qr.expiresIn });
  } catch {
    res.status(500).json({ error: 'Falha ao gerar QR Code.' });
  }
});

router.post('/whatsapp/start', requireAuth, (_req: Request, res: Response) => {
  providerManager.startAccount('primary');
  const account = providerManager.getAccount('primary');
  res.status(202).json({ message: 'Inicialização iniciada.', state: account?.getStatus().state });
});

router.post('/whatsapp/logout', requireAuth, async (_req: Request, res: Response) => {
  await providerManager.logoutAccount('primary');
  res.json({ message: 'Logout realizado.' });
});

router.get('/whatsapp/health', async (_req: Request, res: Response) => {
  const account = providerManager.getAccount('primary');
  if (!account) {
    res.status(503).json({ healthy: false });
    return;
  }
  const healthy = await account.healthCheck();
  res.status(healthy ? 200 : 503).json({ healthy, ...account.getStatus() });
});

// ═══════════════════════════════════════════════════════════
// Contacts
// ═══════════════════════════════════════════════════════════

router.post('/contacts/sync', requireAuth, async (_req: Request, res: Response) => {
  try {
    const result = await runSync();
    cleanOrphanMemberships();
    const dedupe = runDedupe();
    // Push dos contatos ao CRM do backend (fire-and-forget, tolerante a falhas).
    // Import tardio evita dependência circular (routes → provider → crm-sync).
    void import('./crm-sync')
      .then(({ syncAllToCrm }) => syncAllToCrm())
      .catch(() => {
        /* tolerante: sync local já foi feito */
      });
    res.json({ ...result, dedupe, crmSync: 'triggered' });
  } catch (err) {
    res.status(409).json({ error: err instanceof Error ? err.message : 'Falha na sincronização.' });
  }
});

router.post('/contacts/dedupe', requireAuth, (_req: Request, res: Response) => {
  res.json({ dedupe: runDedupe() });
});

router.get('/contacts', requireAuth, (req: Request, res: Response) => {
  const limit = Math.min(Math.max(parseInt(String(req.query.limit ?? '50'), 10) || 50, 1), 500);
  const offset = Math.max(parseInt(String(req.query.offset ?? '0'), 10) || 0, 0);
  const parseFlag = (v: unknown): number | undefined => (v === 'true' ? 1 : v === 'false' ? 0 : undefined);
  const filter = { limit, offset, isGroup: parseFlag(req.query.isGroup), isBusiness: parseFlag(req.query.isBusiness) };
  res.json({ total: countContacts(filter), limit, offset, contacts: listContacts(filter) });
});

router.get('/contacts/:id', (req: Request, res: Response) => {
  const contact = getContactById(Number(req.params.id));
  if (!contact) { res.status(404).json({ error: 'Contato não encontrado.' }); return; }
  res.json(contact);
});

// ═══════════════════════════════════════════════════════════
// Customers
// ═══════════════════════════════════════════════════════════

router.get('/customers', requireAuth, (req: Request, res: Response) => {
  const limit = Math.min(Math.max(parseInt(String(req.query.limit ?? '50'), 10) || 50, 1), 500);
  const offset = Math.max(parseInt(String(req.query.offset ?? '0'), 10) || 0, 0);
  const customerStatus = typeof req.query.customerStatus === 'string' ? req.query.customerStatus : undefined;
  const filter = { limit, offset, customerStatus };
  res.json({ total: countCustomers({ customerStatus }), limit, offset, customers: listCustomers(filter) });
});

router.get('/customers/:id', (req: Request, res: Response) => {
  const customer = getCustomerWithContact(Number(req.params.id));
  if (!customer) { res.status(404).json({ error: 'Cliente não encontrado.' }); return; }
  // Preferência de marketing incluída — backend (automações) consome p/ LGPD.
  const pref = getPreference(customer.id);
  res.json({ ...customer, marketing_status: pref?.marketing_status ?? 'UNKNOWN' });
});

router.post('/customers/:contactId/promote', requireAuth, (req: Request, res: Response) => {
  const contactId = Number(req.params.contactId);
  const contact = getContactById(contactId);
  if (!contact) { res.status(404).json({ error: 'Contato não encontrado.' }); return; }
  const status = typeof req.body?.status === 'string' ? req.body.status : 'UNKNOWN';
  const id = promoteContactToCustomer(contactId, status);
  res.status(201).json(getCustomerById(id));
});

router.put('/customers/:id/status', requireAuth, (req: Request, res: Response) => {
  const id = Number(req.params.id);
  const customer = getCustomerById(id);
  if (!customer) { res.status(404).json({ error: 'Cliente não encontrado.' }); return; }
  const status = typeof req.body?.status === 'string' ? req.body.status : '';
  if (!['CUSTOMER', 'PROSPECT', 'UNKNOWN'].includes(status)) {
    res.status(400).json({ error: 'Status inválido. Use: CUSTOMER, PROSPECT, UNKNOWN.' }); return;
  }
  updateCustomerStatus(id, status);
  res.json(getCustomerById(id));
});

router.post('/customers/sync', requireAuth, async (_req: Request, res: Response) => {
  try {
    const result = await runSync();
    cleanOrphanMemberships();
    const dedupe = runDedupe();
    // Mesma semântica de /contacts/sync: empurra contatos ao CRM.
    void import('./crm-sync')
      .then(({ syncAllToCrm }) => syncAllToCrm())
      .catch(() => {
        /* tolerante */
      });
    res.json({ ...result, dedupe, crmSync: 'triggered' });
  } catch (err) {
    res.status(409).json({ error: err instanceof Error ? err.message : 'Falha na sincronização.' });
  }
});

// ═══════════════════════════════════════════════════════════
// Preferences
// ═══════════════════════════════════════════════════════════

router.post('/customers/:id/opt-in', requireAuth, (req: Request, res: Response) => {
  const id = Number(req.params.id);
  const customer = getCustomerById(id);
  if (!customer) { res.status(404).json({ error: 'Cliente não encontrado.' }); return; }
  const source = typeof req.body?.source === 'string' ? req.body.source : 'manual';
  setOptIn(id, source);
  res.json({ customerId: id, marketingStatus: 'OPTED_IN', source });
});

router.post('/customers/:id/opt-out', requireAuth, (req: Request, res: Response) => {
  const id = Number(req.params.id);
  const customer = getCustomerById(id);
  if (!customer) { res.status(404).json({ error: 'Cliente não encontrado.' }); return; }
  const source = typeof req.body?.source === 'string' ? req.body.source : 'manual';
  setOptOut(id, source);
  res.json({ customerId: id, marketingStatus: 'OPTED_OUT', source });
});

// ═══════════════════════════════════════════════════════════
// Lists
// ═══════════════════════════════════════════════════════════

router.post('/lists/seed', requireAuth, (_req: Request, res: Response) => {
  res.json({ results: seedListsFromRules() });
});

router.get('/lists', requireAuth, (_req: Request, res: Response) => {
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
  if (!name) { res.status(400).json({ error: "Campo 'name' é obrigatório." }); return; }
  try {
    const id = insertList(name, description);
    res.status(201).json(getListById(id));
  } catch (err: unknown) {
    if (String(err).includes('UNIQUE')) { res.status(409).json({ error: 'Já existe uma lista com esse nome.' }); return; }
    throw err;
  }
});

router.get('/lists/:id', (req: Request, res: Response) => {
  const list = getListById(Number(req.params.id));
  if (!list) { res.status(404).json({ error: 'Lista não encontrada.' }); return; }
  res.json({ ...list, contactCount: countListContacts(list.id), customerCount: countListCustomers(list.id) });
});

router.put('/lists/:id', requireAuth, (req: Request, res: Response) => {
  const id = Number(req.params.id);
  if (!getListById(id)) { res.status(404).json({ error: 'Lista não encontrada.' }); return; }
  const name = typeof req.body?.name === 'string' && req.body.name.trim() ? req.body.name.trim() : null;
  const description = typeof req.body?.description === 'string' ? req.body.description.trim() || null : null;
  try {
    renameList(id, name, description);
    res.json(getListById(id));
  } catch (err: unknown) {
    if (String(err).includes('UNIQUE')) { res.status(409).json({ error: 'Já existe uma lista com esse nome.' }); return; }
    throw err;
  }
});

router.delete('/lists/:id', requireAuth, (req: Request, res: Response) => {
  if (!deleteListById(Number(req.params.id))) { res.status(404).json({ error: 'Lista não encontrada.' }); return; }
  res.status(204).send();
});

router.get('/lists/:id/contacts', (req: Request, res: Response) => {
  const id = Number(req.params.id);
  if (!getListById(id)) { res.status(404).json({ error: 'Lista não encontrada.' }); return; }
  res.json({ total: countListContacts(id), contacts: getListContacts(id) });
});

router.post('/lists/:id/contacts/:contactId', requireAuth, (req: Request, res: Response) => {
  const listId = Number(req.params.id);
  const contactId = Number(req.params.contactId);
  if (!getListById(listId)) { res.status(404).json({ error: 'Lista não encontrada.' }); return; }
  if (!getContactById(contactId)) { res.status(404).json({ error: 'Contato não encontrado.' }); return; }
  addContactToList(listId, contactId);
  res.status(201).json({ listId, contactId });
});

router.delete('/lists/:id/contacts/:contactId', requireAuth, (req: Request, res: Response) => {
  const listId = Number(req.params.id);
  const contactId = Number(req.params.contactId);
  if (!removeContactFromList(listId, contactId)) { res.status(404).json({ error: 'Contato não está nessa lista.' }); return; }
  res.status(204).send();
});

router.get('/lists/:id/customers', (req: Request, res: Response) => {
  const id = Number(req.params.id);
  if (!getListById(id)) { res.status(404).json({ error: 'Lista não encontrada.' }); return; }
  res.json({ total: countListCustomers(id), customers: getListCustomers(id) });
});

router.post('/lists/:id/customers/:customerId', requireAuth, (req: Request, res: Response) => {
  const listId = Number(req.params.id);
  const customerId = Number(req.params.customerId);
  if (!getListById(listId)) { res.status(404).json({ error: 'Lista não encontrada.' }); return; }
  if (!getCustomerById(customerId)) { res.status(404).json({ error: 'Cliente não encontrado.' }); return; }
  addCustomerToList(listId, customerId);
  res.status(201).json({ listId, customerId });
});

router.delete('/lists/:id/customers/:customerId', requireAuth, (req: Request, res: Response) => {
  const listId = Number(req.params.id);
  const customerId = Number(req.params.customerId);
  if (!removeCustomerFromList(listId, customerId)) { res.status(404).json({ error: 'Cliente não está nessa lista.' }); return; }
  res.status(204).send();
});

router.post('/lists/:id/sync', requireAuth, async (req: Request, res: Response) => {
  const id = Number(req.params.id);
  if (!getListById(id)) { res.status(404).json({ error: 'Lista não encontrada.' }); return; }
  try {
    const sync = await runSync();
    cleanOrphanMemberships();
    void import('./crm-sync')
      .then(({ syncAllToCrm }) => syncAllToCrm())
      .catch(() => {
        /* tolerante */
      });
    res.json({ sync, listId: id, contactCount: countListContacts(id), customerCount: countListCustomers(id), crmSync: 'triggered' });
  } catch (err) {
    res.status(409).json({ error: err instanceof Error ? err.message : 'Falha na sincronização.' });
  }
});

// ═══════════════════════════════════════════════════════════
// Campaigns
// ═══════════════════════════════════════════════════════════

router.get('/campaigns', requireAuth, (_req: Request, res: Response) => {
  res.json({ total: listCampaigns().length, campaigns: listCampaigns() });
});

router.post('/campaigns', requireAuth, (req: Request, res: Response) => {
  const name = typeof req.body?.name === 'string' ? req.body.name.trim() : '';
  const message = typeof req.body?.message === 'string' ? req.body.message.trim() : '';
  const listId = Number(req.body?.listId);
  if (!name) { res.status(400).json({ error: "Campo 'name' é obrigatório." }); return; }
  if (!message) { res.status(400).json({ error: "Campo 'message' é obrigatório." }); return; }
  if (!listId || !getListById(listId)) { res.status(400).json({ error: "Campo 'listId' obrigatório." }); return; }
  const id = insertCampaign(name, message, listId);
  res.status(201).json(getCampaignById(id));
});

router.get('/campaigns/:id', (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) { res.status(404).json({ error: 'Campanha não encontrada.' }); return; }
  res.json(campaign);
});

router.post('/campaigns/:id/preview', requireAuth, (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) { res.status(404).json({ error: 'Campanha não encontrada.' }); return; }
  if (campaign.status !== 'DRAFT') { res.status(409).json({ error: 'Preview só para DRAFT.' }); return; }
  const preview = createCampaignRecipients(campaign.id, campaign.list_id);
  res.json({ campaignId: campaign.id, name: campaign.name, listId: campaign.list_id, selected: preview.total, eligible: preview.eligible, optedOut: preview.optedOut, blocked: preview.blocked, duplicates: preview.duplicates, message: campaign.message });
});

router.post('/campaigns/:id/start', requireAuth, (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) { res.status(404).json({ error: 'Campanha não encontrada.' }); return; }
  if (campaign.status !== 'DRAFT' && campaign.status !== 'PAUSED') { res.status(409).json({ error: `Status ${campaign.status} não permite início.` }); return; }
  if (campaign.status === 'DRAFT') createCampaignRecipients(campaign.id, campaign.list_id);
  updateCampaignStatus(campaign.id, 'RUNNING');
  res.json({ message: 'Campanha iniciada.', campaign: getCampaignById(campaign.id) });
});

router.post('/campaigns/:id/pause', requireAuth, (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) { res.status(404).json({ error: 'Campanha não encontrada.' }); return; }
  if (campaign.status !== 'RUNNING') { res.status(409).json({ error: `Status ${campaign.status} não permite pausa.` }); return; }
  updateCampaignStatus(campaign.id, 'PAUSED');
  res.json({ message: 'Campanha pausada.', campaign: getCampaignById(campaign.id) });
});

router.post('/campaigns/:id/cancel', requireAuth, (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) { res.status(404).json({ error: 'Campanha não encontrada.' }); return; }
  if (campaign.status === 'COMPLETED' || campaign.status === 'CANCELLED') { res.status(409).json({ error: `Campanha já está ${campaign.status}.` }); return; }
  db.prepare("UPDATE campaign_recipients SET status = 'CANCELLED' WHERE campaign_id = ? AND status IN ('PENDING', 'PROCESSING')").run(campaign.id);
  updateCampaignStatus(campaign.id, 'CANCELLED');
  res.json({ message: 'Campanha cancelada.', campaign: getCampaignById(campaign.id) });
});

router.get('/campaigns/:id/recipients', (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) { res.status(404).json({ error: 'Campanha não encontrada.' }); return; }
  res.json({ total: getCampaignRecipients(campaign.id).length, recipients: getCampaignRecipients(campaign.id) });
});

router.get('/campaigns/:id/results', (req: Request, res: Response) => {
  const campaign = getCampaignById(Number(req.params.id));
  if (!campaign) { res.status(404).json({ error: 'Campanha não encontrada.' }); return; }
  res.json({ campaign: getCampaignById(campaign.id), results: getCampaignResults(campaign.id) });
});
