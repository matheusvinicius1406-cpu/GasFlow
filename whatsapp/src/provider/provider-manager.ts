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
import path from 'node:path';
import { Client, LocalAuth, type Contact } from 'whatsapp-web.js';
import type { WhatsAppContact, WhatsAppProvider, WhatsAppQr, WhatsAppStatus, MessagePayload, SendResult, WhatsAppConnectionState } from './types';

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
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_JITTER_RATIO = 0.3;
const QR_TTL_MS = 60_000;

const HEADLESS = process.env.WHATSAPP_HEADFUL !== 'true';

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
  private state: WhatsAppConnectionState = 'disconnected';
  private qrString: string | null = null;
  private qrGeneratedAtMs: number | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private intentionallyStopped = false;
  private phone: string | null = null;
  private lastConnectedAt: string | null = null;
  private messageListeners: Array<(msg: unknown) => void> = [];

  constructor(config: AccountConfig) {
    this.id = config.id;
    this.name = config.name;
  }

  getStatus(): WhatsAppStatus {
    return {
      state: this.state,
      connected: this.state === 'connected' && this.client !== null,
      hasQr: this.qrString !== null && this.qrGeneratedAtMs !== null,
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
    const client = this.client;
    this.client = null;
    this.state = 'disconnected';
    this.qrString = null;
    this.qrGeneratedAtMs = null;
    this.reconnectAttempts = 0;
    this.phone = null;

    if (client) {
      client.removeAllListeners();
      try { await client.logout(); } catch { /* session may be invalid */ }
      try { await client.destroy(); } catch { /* ignore */ }
    }
    console.log(`[${this.id}] Logout concluído.`);
  }

  async healthCheck(): Promise<boolean> {
    if (!this.isConnected()) return false;
    try {
      const state = await this.client?.getState();
      return state === 'CONNECTED';
    } catch {
      return false;
    }
  }

  async getContacts(): Promise<WhatsAppContact[]> {
    if (!this.isConnected()) throw new Error('WhatsApp não está conectado.');
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
    const chatId = recipient.includes('@') ? recipient : `${recipient}@c.us`;
    try {
      const sent = await this.client!.sendMessage(chatId, message.text);
      return { success: true, messageId: sent.id._serialized };
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      console.error(`[${this.id}] Erro ao enviar para ${chatId}:`, errorMsg);
      return { success: false, error: errorMsg };
    }
  }

  onMessage(listener: (msg: unknown) => void): void {
    this.messageListeners.push(listener);
  }

  // ── Internals ──────────────────────────────────────────

  private createAndInitializeClient(): void {
    this.state = 'connecting';
    this.qrString = null;
    this.qrGeneratedAtMs = null;

    const client = new Client({
      authStrategy: new LocalAuth({ dataPath: this.id === 'primary' ? 'wwebjs_auth/primary' : 'wwebjs_auth/secondary' }),
      puppeteer: {
        headless: HEADLESS,
        executablePath: resolveBrowserExecutable(),
        args: ['--no-sandbox', '--disable-setuid-sandbox'],
      },
    });
    this.client = client;

    client.on('qr', (qr: string) => {
      this.state = 'qr_pending';
      this.qrString = qr;
      this.qrGeneratedAtMs = Date.now();
      console.log(`[${this.id}] QR code gerado.`);
    });

    client.on('authenticated', () => {
      console.log(`[${this.id}] Autenticado.`);
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
      console.log(`[${this.id}] Conectado e pronto.`);
    });

    client.on('auth_failure', (message: string) => {
      console.error(`[${this.id}] Falha de autenticação:`, message);
      this.state = 'disconnected';
      this.qrString = null;
    });

    client.on('disconnected', (reason: string) => {
      console.warn(`[${this.id}] Desconectado:`, reason);
      this.state = 'disconnected';
      this.scheduleReconnect();
    });

    client.on('message', (msg: unknown) => {
      for (const listener of this.messageListeners) {
        try { listener(msg); } catch { /* ignore listener errors */ }
      }
    });

    client.initialize().catch((err) => {
      console.error(`[${this.id}] Erro ao inicializar:`, err);
      this.state = 'disconnected';
      this.scheduleReconnect();
    });
  }

  private scheduleReconnect(): void {
    if (this.intentionallyStopped || this.reconnectTimer || !this.client) return;
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error(`[${this.id}] Máximo de tentativas de reconexão atingido.`);
      void this.teardownClient();
      return;
    }
    const backoff = Math.min(RECONNECT_BASE_DELAY_MS * 2 ** this.reconnectAttempts, 80_000);
    const delay = withJitter(backoff);
    this.reconnectAttempts += 1;
    console.log(`[${this.id}] Reconectando em ${Math.round(delay / 1000)}s (${this.reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}).`);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.teardownClient().then(() => this.createAndInitializeClient());
    }, delay);
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
