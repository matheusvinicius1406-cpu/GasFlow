/**
 * WhatsApp Provider Manager — Multi-Account Support
 *
 * Manages multiple independent WhatsApp sessions.
 * Each account has its own:
 * - Provider instance (whatsapp-web.js Client)
 * - Session storage (wwebjs_auth/{accountId}/)
 * - Connection state
 * - QR code
 * - Reconnection logic
 *
 * GasFlow supports 2 accounts:
 * - "primary" (Marcos Gás)
 * - "secondary" (Marcos Gás 2)
 */

import fs from 'node:fs';
import { Client, LocalAuth, MessageMedia, type Contact } from 'whatsapp-web.js';
import { BaileysEngine } from './baileys-engine';
import type { WhatsAppContact, WhatsAppProvider, WhatsAppQr, WhatsAppStatus, MessagePayload, SendResult, MediaPayload, SendMediaResult, WhatsAppConnectionState } from './types';
import { logger } from '../log';
import { messagesSentTotal, messagesFailedTotal, accountConnected, reconnectAttemptsTotal } from '../metrics';

// ── Types ────────────────────────────────────────────────

export interface AccountConfig {
  id: string;
  name: string;
  sessionDir: string;
}

export interface AccountStatus {
  id: string;
  name: string;
  status: WhatsAppStatus;
  phone: string | null;
  lastConnectedAt: string | null;
}

// ── Constants ────────────────────────────────────────────

const RECONNECT_BASE_DELAY_MS = 5_000;
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_JITTER_RATIO = 0.3;
/** Teto por tentativa (5s * 2^4 = 80s) — após isso mantém 80s com jitter. */
const RECONNECT_MAX_DELAY_MS = 80_000;
const QR_TTL_MS = 60_000;
/** Heartbeat de presença (mantém a sessão viva) — env WA_HEARTBEAT_INTERVAL_MIN. */
const HEARTBEAT_INTERVAL_MIN = Number(process.env.WA_HEARTBEAT_INTERVAL_MIN || 5);
const HEARTBEAT_INTERVAL_MS = Math.max(1, HEARTBEAT_INTERVAL_MIN) * 60_000;
/** URL opcional para alertar em falha crítica (ex.: desconexão permanente). */
const CRITICAL_WEBHOOK_URL = process.env.WA_CRITICAL_WEBHOOK_URL || '';
/** Delay antes do push de contatos ao CRM após conectar (contatos carregam assíncrono). */
const CRM_SYNC_ON_CONNECT_DELAY_MS = 8_000;

const HEADLESS = process.env.WHATSAPP_HEADFUL !== 'true';

// ── Engine selection (Baileys migration) ────────────────

export type EngineName = 'wwebjs' | 'baileys';

/**
 * Motor por conta: WA_ENGINE (global) ou WA_ENGINE_PRIMARY/SECONDARY (override).
 * Default 'baileys' (WebSocket puro). Rollback: WA_ENGINE=wwebjs — sem rebuild,
 * a sessão antiga em wwebjs_auth continua válida.
 */
function resolveEngineForAccount(accountId: string): EngineName {
  const perAccount = (process.env[`WA_ENGINE_${accountId.toUpperCase()}`] || '').toLowerCase();
  const chosen = (perAccount || (process.env.WA_ENGINE || 'baileys')).toLowerCase();
  return chosen === 'wwebjs' ? 'wwebjs' : 'baileys';
}

// ── Default Accounts ─────────────────────────────────────

const DEFAULT_ACCOUNTS: AccountConfig[] = [
  {
    id: 'primary',
    name: process.env.WA_PRIMARY_NAME || 'Marcos Gás',
    sessionDir: process.env.WA_PRIMARY_SESSION || 'wwebjs_auth/primary',
  },
  {
    id: 'secondary',
    name: process.env.WA_SECONDARY_NAME || 'Marcos Gás 2',
    sessionDir: process.env.WA_SECONDARY_SESSION || 'wwebjs_auth/secondary',
  },
];

// ── Helpers ──────────────────────────────────────────────

function withJitter(delayMs: number): number {
  const jitter = delayMs * RECONNECT_JITTER_RATIO * (Math.random() * 2 - 1);
  return Math.max(1_000, Math.round(delayMs + jitter));
}

function resolveBrowserExecutable(): string | undefined {
  if (process.env.WHATSAPP_EXECUTABLE_PATH) return process.env.WHATSAPP_EXECUTABLE_PATH;
  const candidates = [
    'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
    'C:\\Program Files (x86)\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
  ];
  for (const candidate of candidates) {
    try {
      if (fs.existsSync(candidate)) return candidate;
    } catch { /* ignore */ }
  }
  return undefined;
}

function toProviderContact(contact: Contact): WhatsAppContact {
  const jid = contact.id._serialized;
  const isGroup = jid.endsWith('@g.us');
  const businessDescription = (
    contact as unknown as { businessProfile?: { description?: string } }
  ).businessProfile?.description;

  return {
    jid,
    phone: isGroup ? null : ((contact as unknown as { number?: string }).number ?? null),
    name: typeof contact.name === 'string' && contact.name.length > 0 ? contact.name : null,
    pushName: typeof contact.pushname === 'string' && contact.pushname.length > 0 ? contact.pushname : null,
    businessName: typeof businessDescription === 'string' && businessDescription.length > 0 ? businessDescription : null,
    isBusiness: Boolean(contact.isBusiness),
    isGroup,
  };
}

// ── AccountInstance ──────────────────────────────────────

class AccountInstance implements WhatsAppProvider {
  readonly id: string;
  readonly name: string;
  private client: Client | null = null;
  private baileys: BaileysEngine | null = null;
  private state: WhatsAppConnectionState = 'disconnected';
  private qrString: string | null = null;
  private qrGeneratedAtMs: number | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private intentionallyStopped = false;
  private heartbeatTimer: NodeJS.Timeout | null = null;
  private phone: string | null = null;
  private lastConnectedAt: string | null = null;
  private messageListeners: Array<(msg: unknown) => void> = [];

  constructor(config: AccountConfig) {
    this.id = config.id;
    this.name = config.name;
    this.engine = resolveEngineForAccount(config.id);
    logger.info('account.engine_selected', { accountId: this.id, engine: this.engine });
  }

  private engine: EngineName;

  getStatus(): WhatsAppStatus {
    // hasQr expira em 60s (mesmo TTL do endpoint /qr) — sem isso o FE
    // mostrava QR "disponível" que já tinha expirado (404 ao buscar).
    const qrFresh = this.qrString !== null && this.qrGeneratedAtMs !== null && Date.now() - this.qrGeneratedAtMs < QR_TTL_MS;
    return {
      state: this.state,
      connected: this.state === 'connected' && (this.engine === 'baileys' ? this.baileys !== null : this.client !== null),
      hasQr: qrFresh,
    };
  }

  getQr(): WhatsAppQr | null {
    if (!this.qrString || this.qrGeneratedAtMs === null) return null;
    const expiresAtMs = this.qrGeneratedAtMs + QR_TTL_MS;
    const expiresIn = Math.max(0, Math.round((expiresAtMs - Date.now()) / 1000));
    return {
      qr: this.qrString,
      generatedAt: new Date(this.qrGeneratedAtMs).toISOString(),
      expiresAt: new Date(expiresAtMs).toISOString(),
      expiresIn,
    };
  }

  isConnected(): boolean {
    return this.getStatus().connected;
  }

  getPhone(): string | null {
    return this.phone;
  }

  getLastConnectedAt(): string | null {
    return this.lastConnectedAt;
  }

  getAccountStatus(): AccountStatus {
    return {
      id: this.id,
      name: this.name,
      status: this.getStatus(),
      phone: this.phone,
      lastConnectedAt: this.lastConnectedAt,
    };
  }

  start(): void {
    if (this.client || this.reconnectTimer) return;
    this.intentionallyStopped = false;
    this.createAndInitializeClient();
  }

  async stop(): Promise<void> {
    this.intentionallyStopped = true;
    this.clearReconnectTimer();
    await this.teardownClient();
    this.state = 'disconnected';
  }

  async logout(): Promise<void> {
    this.intentionallyStopped = true;
    this.clearReconnectTimer();
    this.stopHeartbeat();
    this.state = 'disconnected';
    this.qrString = null;
    this.qrGeneratedAtMs = null;
    this.reconnectAttempts = 0;
    this.phone = null;

    const engine = this.baileys;
    this.baileys = null;
    if (engine) {
      try { await engine.logout(); } catch { /* session may be invalid */ }
    }
    const client = this.client;
    this.client = null;
    if (client) {
      client.removeAllListeners();
      try { await client.logout(); } catch { /* session may be invalid */ }
      try { await client.destroy(); } catch { /* ignore */ }
    }
    logger.info('account.logout_completed', { accountId: this.id });
  }

  async healthCheck(): Promise<boolean> {
    if (!this.isConnected()) return false;
    if (this.engine === 'baileys') return this.baileys?.healthPing() ?? false;
    try {
      const state = await this.client?.getState();
      return state === 'CONNECTED';
    } catch {
      return false;
    }
  }

  async getContacts(): Promise<WhatsAppContact[]> {
    if (!this.isConnected()) throw new Error('WhatsApp não está conectado.');
    if (this.engine === 'baileys') {
      // Baileys não mantém catálogo rico — JIDs 1:1 visíveis no socket.
      return this.baileys?.getJids().map((jid) => ({
        jid,
        phone: jid.split('@')[0] ?? null,
        name: null,
        pushName: null,
        businessName: null,
        isBusiness: false,
        isGroup: false,
      })) ?? [];
    }
    const contacts = await this.client!.getContacts();
    return contacts
      .filter((c) => {
        const jid = c.id._serialized;
        return (
          !jid.endsWith('@broadcast') &&
          !jid.endsWith('@c.us.status') &&
          !jid.endsWith('@lid') &&
          jid.endsWith('@c.us')
        );
      })
      .map(toProviderContact);
  }

  async sendMessage(recipient: string, message: MessagePayload): Promise<SendResult> {
    if (!this.isConnected()) {
      return { success: false, error: 'WhatsApp não está conectado.' };
    }
    // Sufixo decidido pelo ENGINE — @c.us é do wwebjs; Baileys usa @s.whatsapp.net.
    const chatId = recipient.includes('@') ? recipient : `${recipient}${this.engine === 'baileys' ? '@s.whatsapp.net' : '@c.us'}`;
    if (this.engine === 'baileys') {
      try {
        const sent = await this.baileys!.sendText(chatId, message.text);
        messagesSentTotal.inc({ account: this.id });
        return { success: true, messageId: sent.id ?? 'unknown' };
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Unknown error';
        messagesFailedTotal.inc({ account: this.id, reason: 'send_error' });
        logger.error('message.send.failed', { account: this.id, to: chatId, error: errorMsg });
        return { success: false, error: errorMsg };
      }
    }
    try {
      const sent = await this.client!.sendMessage(chatId, message.text);
      messagesSentTotal.inc({ account: this.id });
      return { success: true, messageId: sent.id._serialized };
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      logger.error('message.send.failed', { account: this.id, to: chatId, error: errorMsg });
      return { success: false, error: errorMsg };
    }
  }

  async sendMedia(recipient: string, media: MediaPayload): Promise<SendMediaResult> {
    if (!this.isConnected()) {
      return { success: false, error: 'WhatsApp não está conectado.' };
    }
    if (!media.data || !media.mimetype) {
      return { success: false, error: 'Mídia inválida: data e mimetype são obrigatórios.' };
    }
    const chatId = recipient.includes('@') ? recipient : `${recipient}${this.engine === 'baileys' ? '@s.whatsapp.net' : '@c.us'}`;
    if (this.engine === 'baileys') {
      try {
        const sent = await this.baileys!.sendMediaBase64(
          chatId, media.data, media.mimetype, media.filename, media.caption,
        );
        messagesSentTotal.inc({ account: this.id });
        logger.info('message.media.sent', { account: this.id, to: chatId, mimetype: media.mimetype });
        return { success: true, messageId: sent.id ?? 'unknown' };
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Unknown error';
        messagesFailedTotal.inc({ account: this.id, reason: 'media_error' });
        logger.error('message.media.send.failed', { account: this.id, to: chatId, error: errorMsg });
        return { success: false, error: errorMsg };
      }
    }
    try {
      const file = new MessageMedia(media.mimetype, media.data, media.filename);
      const sent = await this.client!.sendMessage(chatId, file, {
        caption: media.caption || undefined,
      });
      logger.info('message.media.sent', { account: this.id, to: chatId, mimetype: media.mimetype });
      return { success: true, messageId: sent.id._serialized };
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      logger.error('message.media.send.failed', { account: this.id, to: chatId, error: errorMsg });
      return { success: false, error: errorMsg };
    }
  }

  getReconnectStats(): { attempts: number; maxAttempts: number; lastAttemptAt: string | null } {
    return { attempts: this.reconnectAttempts, maxAttempts: MAX_RECONNECT_ATTEMPTS, lastAttemptAt: this.lastReconnectAt };
  }

  onMessage(listener: (msg: unknown) => void): void {
    this.messageListeners.push(listener);
  }

  // ── Internals ──────────────────────────────────────────

  private createAndInitializeClient(): void {
    this.state = 'connecting';
    this.qrString = null;
    this.qrGeneratedAtMs = null;

    if (this.engine === 'baileys') {
      this.createAndInitializeBaileys();
      return;
    }

    const client = new Client({
      authStrategy: new LocalAuth({ dataPath: this.id === 'primary' ? 'wwebjs_auth/primary' : 'wwebjs_auth/secondary' }),
      puppeteer: {
        headless: HEADLESS,
        executablePath: resolveBrowserExecutable(),
        args: [
          '--no-sandbox',
          '--disable-setuid-sandbox',
          // Docker padroniza /dev/shm em 64M — sem essa flag o Chromium falha
          // ao lançar e o whatsapp-web.js nunca chega ao estado qr_pending.
          '--disable-dev-shm-usage',
        ],
      },
    });
    this.client = client;

    client.on('qr', (qr: string) => {
      this.state = 'qr_pending';
      this.qrString = qr;
      this.qrGeneratedAtMs = Date.now();
      logger.info('account.qr_generated', { accountId: this.id, engine: this.engine });
    });

    client.on('authenticated', () => {
      logger.info('account.authenticated', { accountId: this.id, engine: this.engine });
      this.reconnectAttempts = 0;
    });

    client.on('ready', () => {
      this.state = 'connected';
      this.qrString = null;
      this.reconnectAttempts = 0;
      this.lastConnectedAt = new Date().toISOString();
      // Try to get phone number
      try {
        const info = client.info;
        if (info?.wid?.user) {
          this.phone = info.wid.user;
        }
      } catch { /* ignore */ }
      accountConnected.set({ account: this.id, engine: this.engine }, 1);
      this.startHeartbeat();
      logger.info('account.connected', { account: this.id, phone: this.phone });
      this.scheduleCrmSync();
    });

    client.on('auth_failure', (message: string) => {
      logger.error('account.auth_failed', { account: this.id, message });
      this.state = 'disconnected';
      this.qrString = null;
    });

    client.on('disconnected', (reason: string) => {
      logger.warn('account.disconnected', { account: this.id, reason });
      this.state = 'disconnected';
      this.stopHeartbeat();
      accountConnected.set({ account: this.id, engine: this.engine }, 0);
      this.scheduleReconnect();
    });

    client.on('message', (msg: unknown) => {
      for (const listener of this.messageListeners) {
        try { listener(msg); } catch { /* ignore listener errors */ }
      }
    });

    client.initialize().catch((err) => {
      logger.error('account.initialize.failed', { account: this.id, error: err instanceof Error ? err.message : String(err) });
      this.state = 'disconnected';
      this.scheduleReconnect();
    });
  }

  /** Inicialização via Baileys (WebSocket puro, sem Chromium). */
  private createAndInitializeBaileys(): void {
    const engine = new BaileysEngine({ accountId: this.id });
    this.baileys = engine;

    const dispatch = (event: string, payload?: unknown): void => {
      switch (event) {
        case 'qr':
          this.state = 'qr_pending';
          this.qrString = String(payload ?? '');
          this.qrGeneratedAtMs = Date.now();
          logger.info('account.qr_generated', { accountId: this.id, engine: 'baileys' });
          break;
        case 'authenticated':
          logger.info('account.authenticated', { accountId: this.id, engine: 'baileys' });
          this.reconnectAttempts = 0;
          break;
        case 'ready':
          this.state = 'connected';
          this.qrString = null;
          this.qrGeneratedAtMs = null;
          this.reconnectAttempts = 0;
          this.lastConnectedAt = new Date().toISOString();
          this.phone = (payload as { phone?: string | null } | undefined)?.phone ?? null;
          accountConnected.set({ account: this.id, engine: this.engine }, 1);
          this.startHeartbeat();
          logger.info('account.connected', { account: this.id, phone: this.phone, engine: 'baileys' });
          this.scheduleCrmSync();
          break;
        case 'disconnected':
          logger.warn('account.disconnected', { account: this.id, reason: String(payload ?? 'unknown'), engine: 'baileys' });
          this.state = 'disconnected';
          this.stopHeartbeat();
          accountConnected.set({ account: this.id, engine: this.engine }, 0);
          this.scheduleReconnect();
          break;
        case 'logged_out':
          // Sessão deslogada no servidor (creds locais viram lixo). Reconectar
          // com as mesmas creds dá Bad MAC/No session record até esgotar as
          // tentativas. Auto-recovery: apaga credenciais e recomeça com QR.
          logger.warn('account.logged_out', { account: this.id, engine: 'baileys', action: 'wipe-creds-and-restart' });
          this.state = 'disconnected';
          this.stopHeartbeat();
          accountConnected.set({ account: this.id, engine: this.engine }, 0);
          this.reconnectAttempts = 0;
          void this.teardownClient().then(() => {
            if (!this.intentionallyStopped) this.createAndInitializeClient();
          });
          break;
        case 'message':
          for (const listener of this.messageListeners) {
            try { listener(payload); } catch { /* ignore listener errors */ }
          }
          break;
      }
    };

    engine.connect(dispatch).catch((err) => {
      logger.error('account.initialize.failed', {
        account: this.id,
        engine: 'baileys',
        error: err instanceof Error ? err.message : String(err),
      });
      this.state = 'disconnected';
      this.scheduleReconnect();
    });
  }

  // ── Heartbeat (mantém a sessão ativa) ────────────────

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.state !== 'connected') return;
      try {
        if (this.engine === 'baileys') {
          // Baileys: sendPresenceAvailable direto no socket ( antes só wwebjs
          // tinha heartbeat — o guard !this.client pulava o Baileys).
          const sock = (this.baileys as unknown as { sock?: { sendPresenceAvailable?: () => Promise<void> } | null } | null)?.sock;
          sock?.sendPresenceAvailable?.()
            .then(() => logger.debug('account.heartbeat', { account: this.id }))
            .catch((err: unknown) =>
              logger.warn('account.heartbeat.failed', {
                account: this.id,
                error: err instanceof Error ? err.message : String(err),
              }),
            );
          return;
        }
        this.client
          ?.sendPresenceAvailable()
          .then(() => logger.debug('account.heartbeat', { account: this.id }))
          .catch((err: unknown) =>
            logger.warn('account.heartbeat.failed', {
              account: this.id,
              error: err instanceof Error ? err.message : String(err),
            }),
          );
      } catch { /* nunca derrubar o processo por heartbeat */ }
    }, HEARTBEAT_INTERVAL_MS);
    this.heartbeatTimer.unref?.();
    logger.debug('account.heartbeat.started', { account: this.id, intervalMs: HEARTBEAT_INTERVAL_MS });
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  // ── CRM sync (push de contatos ao backend ao conectar) ──

  private crmSyncTimer: NodeJS.Timeout | null = null;

  /**
   * Agenda o push de contatos ao CRM logo após a conta conectar.
   * Debounce de alguns segundos (contatos do provider podem demorar a
   * carregar) e idempotente: reconexões em janela curta disparam 1 push.
   * Tolerante a falhas: backend fora do ar nunca afeta a sessão.
   */
  private scheduleCrmSync(): void {
    if (this.crmSyncTimer) clearTimeout(this.crmSyncTimer);
    this.crmSyncTimer = setTimeout(() => {
      this.crmSyncTimer = null;
      if (this.state !== 'connected') return;
      void import('../crm-sync')
        .then(({ syncAccountToCrm }) => syncAccountToCrm(this.id))
        .then((result) => {
          if (!result.ok && result.error) {
            logger.warn('crm-sync.connect.skipped', { account: this.id, error: result.error });
          } else {
            logger.info('crm-sync.connect.done', { account: this.id, sent: result.sent, batches: result.batches });
          }
        })
        .catch((err: unknown) =>
          logger.warn('crm-sync.connect.failed', {
            account: this.id,
            error: err instanceof Error ? err.message : String(err),
          }),
        );
    }, CRM_SYNC_ON_CONNECT_DELAY_MS);
    this.crmSyncTimer.unref?.();
  }

  // ── Reconnect ─────────────────────────────────────────

  private lastReconnectAt: string | null = null;

  private scheduleReconnect(): void {
    if (this.intentionallyStopped || this.reconnectTimer) return;
    // Runtime ativo: client (wwebjs) ou engine (baileys) — sem ele não há o que reconectar.
    const hasRuntime = this.engine === 'baileys' ? this.baileys !== null : this.client !== null;
    if (!hasRuntime) return;
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      logger.error('account.reconnect.exhausted', { account: this.id, attempts: this.reconnectAttempts });
      void this.teardownClient();
      void this.notifyCriticalFailure('max_reconnect_attempts');
      return;
    }
    const backoff = Math.min(RECONNECT_BASE_DELAY_MS * 2 ** this.reconnectAttempts, RECONNECT_MAX_DELAY_MS);
    const delay = withJitter(backoff);
    this.reconnectAttempts += 1;
    reconnectAttemptsTotal.inc({ account: this.id });
    this.lastReconnectAt = new Date().toISOString();
    logger.warn('account.reconnect.scheduled', {
      account: this.id,
      attempt: this.reconnectAttempts,
      maxAttempts: MAX_RECONNECT_ATTEMPTS,
      delayMs: delay,
    });
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.teardownClient().then(() => this.createAndInitializeClient());
    }, delay);
  }

  /** Alerta opcional (fire-and-forget) em falha crítica — ex.: webhook/slack. */
  private async notifyCriticalFailure(kind: string): Promise<void> {
    if (!CRITICAL_WEBHOOK_URL) return;
    try {
      const body = {
        event: 'whatsapp.critical_failure',
        account: this.id,
        kind,
        state: this.state,
        at: new Date().toISOString(),
      };
      await fetch(CRITICAL_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      logger.info('account.critical_alert.sent', { account: this.id, kind });
    } catch (err) {
      logger.error('account.critical_alert.failed', {
        account: this.id,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private async teardownClient(): Promise<void> {
    const client = this.client;
    this.client = null;
    const engine = this.baileys;
    this.baileys = null;
    this.stopHeartbeat();
    if (engine) {
      try { await engine.disconnect(); } catch { /* ignore */ }
    }
    if (!client) return;
    client.removeAllListeners();
    try { await client.destroy(); } catch { /* ignore */ }
  }
}

// ── ProviderManager ──────────────────────────────────────

export class ProviderManager {
  private accounts: Map<string, AccountInstance> = new Map();

  constructor(configs: AccountConfig[] = DEFAULT_ACCOUNTS) {
    for (const config of configs) {
      this.accounts.set(config.id, new AccountInstance(config));
    }
  }

  getAccount(id: string): AccountInstance | undefined {
    return this.accounts.get(id);
  }

  getAllAccounts(): AccountStatus[] {
    return Array.from(this.accounts.values()).map((a) => a.getAccountStatus());
  }

  getAccountIds(): string[] {
    return Array.from(this.accounts.keys());
  }

  startAccount(id: string): void {
    const account = this.accounts.get(id);
    if (!account) throw new Error(`Conta ${id} não encontrada.`);
    account.start();
  }

  stopAccount(id: string): Promise<void> {
    const account = this.accounts.get(id);
    if (!account) throw new Error(`Conta ${id} não encontrada.`);
    return account.stop();
  }

  logoutAccount(id: string): Promise<void> {
    const account = this.accounts.get(id);
    if (!account) throw new Error(`Conta ${id} não encontrada.`);
    return account.logout();
  }

  async stopAll(): Promise<void> {
    for (const account of this.accounts.values()) {
      await account.stop();
    }
  }
}

// ── Singleton ────────────────────────────────────────────

export const providerManager = new ProviderManager();

// ── Messaging (FASE 5.24) ──────────────────────────────

export interface SendMessageOptions {
  accountId: string;
  recipient: string;
  text: string;
  idempotencyKey?: string;
}

export interface SendMessageResult {
  success: boolean;
  messageId?: string;
  error?: string;
  errorCode?: string;
}

/**
 * Send a message via a specific account.
 * This is the ONLY public messaging entry point in ProviderManager.
 */
export async function sendMessage(options: SendMessageOptions): Promise<SendMessageResult> {
  const { accountId, recipient, text } = options;

  // Validate account
  const account = providerManager.getAccount(accountId);
  if (!account) {
    return { success: false, error: 'Conta não encontrada.', errorCode: 'ACCOUNT_NOT_FOUND' };
  }

  // Validate connected
  if (!account.isConnected()) {
    return { success: false, error: 'Conta não está conectada.', errorCode: 'ACCOUNT_NOT_CONNECTED' };
  }

  // Validate message
  if (!text || text.trim().length === 0) {
    return { success: false, error: 'Mensagem não pode ser vazia.', errorCode: 'EMPTY_MESSAGE' };
  }

  // Send via provider
  const result = await account.sendMessage(recipient, { text: text.trim() });
  return {
    success: result.success,
    messageId: result.messageId,
    error: result.error,
    errorCode: result.success ? undefined : 'MESSAGE_SEND_FAILED',
  };
}
