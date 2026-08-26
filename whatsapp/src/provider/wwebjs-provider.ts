import fs from 'node:fs';
import { Client, LocalAuth, type Contact } from 'whatsapp-web.js';
import type { MessagePayload, SendResult, WhatsAppContact, WhatsAppProvider, WhatsAppQr, WhatsAppStatus } from './types';

/**
 * Provider baseado em whatsapp-web.js (Apache-2.0).
 *
 * Padrões adaptados de projetos maduros (sem cópia de código):
 * - Backoff exponencial COM jitter aleatório (técnica usada pelo Baileys,
 *   MIT — github.com/WhiskeySockets/Baileys, socket.ts) para evitar
 *   reconexões em rajada.
 * - Health check leve via getState() (padrão /session-state do WPPConnect
 *   Apache-2.0 e /health do WAHA).
 * - Ciclo de vida qr -> authenticated -> ready -> disconnected conforme a
 *   documentação oficial do whatsapp-web.js.
 */

const RECONNECT_BASE_DELAY_MS = 5_000;
const MAX_RECONNECT_ATTEMPTS = 5;
/** Jitter máximo relativo aplicado ao delay calculado. */
const RECONNECT_JITTER_RATIO = 0.3;
/** TTL do QR oficial do WhatsApp Web antes de rotacionar. */
const QR_TTL_MS = 60_000;

export type SessionState = 'disconnected' | 'connecting' | 'qr_pending' | 'connected';

function resolveBrowserExecutable(): string | undefined {
  if (process.env.WHATSAPP_EXECUTABLE_PATH) return process.env.WHATSAPP_EXECUTABLE_PATH;
  const candidates = [
    'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
    'C:\\Program Files (x86)\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
  ];
  for (const candidate of candidates) {
    try {
      if (fs.existsSync(candidate)) return candidate;
    } catch {
      // ignore and try next
    }
  }
  return undefined;
}

/**
 * Headless por padrão: o QR oficial é exibido na nossa página GET /connect.
 * WHATSAPP_HEADFUL=true reexibe a janela real do WhatsApp Web (debug).
 */
const HEADLESS = process.env.WHATSAPP_HEADFUL !== 'true';

function withJitter(delayMs: number): number {
  const jitter = delayMs * RECONNECT_JITTER_RATIO * (Math.random() * 2 - 1);
  return Math.max(1_000, Math.round(delayMs + jitter));
}

/** Converte o contato específico da lib para o formato neutro do provider. */
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

class WhatsAppWebJsProvider implements WhatsAppProvider {
  private client: Client | null = null;
  private state: SessionState = 'disconnected';
  private qrString: string | null = null;
  private qrGeneratedAtMs: number | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private intentionallyStopped = false;

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

  start(): void {
    if (this.client || this.reconnectTimer) return; // já rodando ou agendado
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

    if (client) {
      client.removeAllListeners();
      try {
        await client.logout(); // invalida a sessão no servidor do WhatsApp
      } catch {
        // sessão pode já estar inválida
      }
      try {
        await client.destroy();
      } catch {
        // ignore
      }
    }
    console.log('[whatsapp] Logout concluído.');
  }

  async healthCheck(): Promise<boolean> {
    if (!this.isConnected()) return false;
    try {
      const state = await this.client?.getState();
      // WAState.CONNECTED é o único estado que indica sessão ativa.
      return state === 'CONNECTED';
    } catch (err) {
      console.warn('[whatsapp] healthCheck falhou:', err instanceof Error ? err.message : err);
      return false;
    }
  }

  async getContacts(): Promise<WhatsAppContact[]> {
    if (!this.isConnected()) throw new Error('WhatsApp não está conectado.');
    const contacts = await this.client!.getContacts();
    // Filta contatos internos/inválidos: status, broadcasts e JIDs @lid
    // (identificador interno do multi-device — o "user" não é um telefone real).
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

    // Normalize recipient: ensure it ends with @c.us
    const chatId = recipient.includes('@') ? recipient : `${recipient}@c.us`;

    try {
      const sent = await this.client!.sendMessage(chatId, message.text);
      return { success: true, messageId: sent.id._serialized };
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      console.error(`[whatsapp] Erro ao enviar para ${chatId}:`, errorMsg);
      return { success: false, error: errorMsg };
    }
  }

  // ------------------------------------------------------------------
  // internals
  // ------------------------------------------------------------------

  private createAndInitializeClient(): void {
    this.state = 'connecting';
    this.qrString = null;
    this.qrGeneratedAtMs = null;

    const client = new Client({
      authStrategy: new LocalAuth({ dataPath: 'wwebjs_auth' }),
      puppeteer: {
        headless: HEADLESS,
        executablePath: resolveBrowserExecutable(),
        args: ['--no-sandbox', '--disable-setuid-sandbox'],
      },
    });
    this.client = client;

    client.on('qr', (qr: string) => {
      // O mesmo evento dispara novamente quando web.whatsapp.com rotaciona o código.
      this.state = 'qr_pending';
      this.qrString = qr;
      this.qrGeneratedAtMs = Date.now();
      console.log('[whatsapp] QR code gerado. Aguardando leitura.');
    });

    client.on('authenticated', () => {
      console.log('[whatsapp] Autenticado.');
      this.reconnectAttempts = 0;
    });

    client.on('ready', () => {
      this.state = 'connected';
      this.qrString = null;
      this.reconnectAttempts = 0;
      console.log('[whatsapp] Conectado e pronto.');
    });

    client.on('auth_failure', (message: string) => {
      console.error('[whatsapp] Falha de autenticação:', message);
      this.state = 'disconnected';
      this.qrString = null;
    });

    client.on('disconnected', (reason: string) => {
      console.warn('[whatsapp] Desconectado:', reason);
      this.state = 'disconnected';
      this.scheduleReconnect();
    });

    client.initialize().catch((err) => {
      console.error('[whatsapp] Erro ao inicializar cliente:', err);
      this.state = 'disconnected';
      this.scheduleReconnect();
    });
  }

  private scheduleReconnect(): void {
    if (this.intentionallyStopped || this.reconnectTimer || !this.client) return;

    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error(
        '[whatsapp] Máximo de tentativas de reconexão atingido. Use POST /api/whatsapp/start para tentar novamente.',
      );
      void this.teardownClient();
      return;
    }

    const backoff = Math.min(RECONNECT_BASE_DELAY_MS * 2 ** this.reconnectAttempts, 80_000);
    const delay = withJitter(backoff);
    this.reconnectAttempts += 1;
    console.log(
      `[whatsapp] Reconectando em ${Math.round(delay / 1000)}s (tentativa ${this.reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}).`,
    );
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
    try {
      await client.destroy();
    } catch {
      // ignore: cliente pode já estar morto
    }
  }
}

export const whatsappProvider: WhatsAppProvider = new WhatsAppWebJsProvider();
