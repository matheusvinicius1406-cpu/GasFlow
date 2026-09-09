/**
 * Baileys Engine — WebSocket puro (sem Chromium/Puppeteer).
 *
 * Implementa a MESMA superfície que o whatsapp-web.js expunha ao
 * provider-manager, para que manager, broadcast, incoming.ts, rotas e
 * testes continuem funcionando sem mudanças de comportamento:
 *
 *   connect(onEvent) — inicia a conexão (async interno, eventos via callback)
 *   disconnect()     — encerra mantendo a sessão em disco
 *   logout()         — invalida a sessão no servidor e descarta credenciais
 *   sendText(to, text)                  → { id }
 *   sendMediaBase64(to, base64, mime)   → { id }
 *   getJids()                           → JIDs de contatos 1:1
 *   healthPing()                        → boolean
 *   qr / phone / connected / state      → getters
 *
 * Eventos (via callback onEvent):
 *   'qr'             (qr: string)
 *   'authenticated'  ()
 *   'ready'          (info: { phone: string | null })
 *   'disconnected'   (reason: string)
 *   'message'        (msg: { id, from, fromMe, author?, body, type, timestamp })
 *
 * Sessão: useMultiFileAuthState em BAILEYS_AUTH_DIR/{accountId} (creds.json
 * + keys). A sessão do wwebjs NÃO é compatível — novo pareamento por QR
 * (ou pairing code) é necessário na primeira execução.
 */

import fs from 'node:fs';
import path from 'node:path';
import {
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  makeWASocket,
  useMultiFileAuthState,
  downloadMediaMessage,
  type WASocket,
  type AnyMessageContent,
  type UserFacingSocketConfig,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import pino from 'pino';

/** Logger dedicado do Baileys (pino) — padrão da lib; silencioso por padrão. */
const baileysLogger = pino({ level: process.env.BAILEYS_LOG_LEVEL || 'error' });

const AUTH_DIR = process.env.BAILEYS_AUTH_DIR || path.join(process.cwd(), 'baileys_auth');

export type EngineEvent =
  | 'qr'
  | 'authenticated'
  | 'ready'
  | 'disconnected'
  | 'message';

export interface BaileysIncomingMessage {
  id?: string | { _serialized?: string };
  from?: string;
  fromMe?: boolean;
  author?: string;
  body?: string;
  type?: string;
  timestamp?: number;
}

export interface BaileysEngineOptions {
  accountId: string;
  /** Chrome/browser version fixa evita drops de conexão por version mismatch. */
  browser?: [string, string, string];
  /** Pairing code (alternativa ao QR) — número do próprio bot. */
  pairingCodePhone?: string;
}

export class BaileysEngine {
  private sock: WASocket | null = null;  // exposto (leitura) p/ heartbeat do manager
  private connected = false;
  private qrString: string | null = null;
  private phone: string | null = null;
  private state: 'disconnected' | 'connecting' | 'qr_pending' | 'connected' = 'disconnected';
  private intentionallyStopped = false;
  private readonly accountId: string;
  private readonly browser: [string, string, string];
  private readonly pairingCodePhone?: string;

  constructor(opts: BaileysEngineOptions) {
    this.accountId = opts.accountId;
    this.browser = opts.browser ?? ['GasFlow', 'Chrome', '120.0.0.0'];
    this.pairingCodePhone = opts.pairingCodePhone || process.env.WA_PAIRING_CODE_PHONE || undefined;
  }

  // ── Getters (superfície do manager) ────────────────────

  get isConnected(): boolean {
    return this.connected;
  }

  get stateName(): 'disconnected' | 'connecting' | 'qr_pending' | 'connected' {
    return this.state;
  }

  get qr(): string | null {
    return this.qrString;
  }

  get phoneNumber(): string | null {
    return this.phone;
  }

  // ── Ciclo de vida ──────────────────────────────────────

  /** Inicia a conexão. Erros de boot são logados e reportados como disconnect. */
  async connect(onEvent: (event: EngineEvent, payload?: unknown) => void): Promise<void> {
    this.intentionallyStopped = false;
    this.state = 'connecting';
    this.qrString = null;

    const sessionDir = path.join(AUTH_DIR, this.accountId);
    fs.mkdirSync(sessionDir, { recursive: true });
    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);

    let version: [number, number, number] | undefined;
    try {
      ({ version } = await fetchLatestBaileysVersion());
    } catch {
      // Sem acesso à internet no boot — Baileys usa a versão default.
    }

    const config: UserFacingSocketConfig = {
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, baileysLogger),
      },
      version,
      browser: this.browser,
      syncFullHistory: false,
      markOnlineOnConnect: true,
      defaultQueryTimeoutMs: 60_000,
      logger: baileysLogger,
    };

    const sock = makeWASocket(config);
    this.sock = sock;

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        this.qrString = qr;
        this.state = 'qr_pending';
        onEvent('qr', qr);
      }

      if (connection === 'connecting') {
        // Pairing code: alternativa ao QR quando configurado (só na 1ª vez).
        if (!this.qrString && this.pairingCodePhone && !sock.authState.creds.registered) {
          try {
            const code = await sock.requestPairingCode(this.pairingCodePhone);
            console.log(`[${this.accountId}] Pairing code: ${code}`);
          } catch (err) {
            console.warn(`[${this.accountId}] Pairing code falhou: ${err instanceof Error ? err.message : String(err)}`);
          }
        }
      }

      if (connection === 'open') {
        this.connected = true;
        this.state = 'connected';
        this.qrString = null;
        this.phone = sock.user?.id?.split(':')[0] ?? null;
        onEvent('ready', { phone: this.phone });
      }

      if (connection === 'close') {
        this.connected = false;
        const statusCode = (lastDisconnect?.error as Boom | undefined)?.output?.statusCode;
        const reason = statusCode !== undefined ? String(statusCode) : 'unknown';
        const loggedOut = statusCode === DisconnectReason.loggedOut;

        if (this.intentionallyStopped) return;

        if (loggedOut) {
          this.state = 'disconnected';
          onEvent('disconnected', 'logged_out');
          return;
        }
        // Reconexão: o próprio manager agenda retry via connect() novamente.
        this.state = 'disconnected';
        onEvent('disconnected', reason);
      }
    });

    sock.ev.on('messages.upsert', async ({ messages }) => {
      for (const msg of messages) {
        // mensagens de estado/protocolo sem conteúdo — ignora
        if (!msg.message) continue;
        onEvent('message', toIncomingShape(msg));
      }
    });
  }

  /** Encerra mantendo a sessão salva (equivalente a client.destroy()). */
  async disconnect(): Promise<void> {
    this.intentionallyStopped = true;
    this.connected = false;
    this.state = 'disconnected';
    const sock = this.sock;
    this.sock = null;
    if (!sock) return;
    try {
      // TypedEventEmitter do Baileys exige nome de evento no TS; em runtime é um EventEmitter comum.
      (sock.ev as unknown as { removeAllListeners: () => void }).removeAllListeners();
      sock.end(new Error('intentional disconnect'));
    } catch { /* socket já fechado */ }
  }

  /** Invalida a sessão no servidor e apaga credenciais locais. */
  async logout(): Promise<void> {
    const sock = this.sock;
    try {
      if (sock) await sock.logout();
    } catch { /* sessão pode já estar inválida */ }
    await this.disconnect();
    try {
      fs.rmSync(path.join(AUTH_DIR, this.accountId), { recursive: true, force: true });
    } catch { /* ignore */ }
    this.phone = null;
    this.qrString = null;
  }

  // ── Envio ──────────────────────────────────────────────

  normalizeJid(to: string): string {
    if (to.includes('@')) return to;
    return `${to}@s.whatsapp.net`;
  }

  async sendText(to: string, text: string): Promise<{ id: string | undefined }> {
    if (!this.sock || !this.connected) throw new Error('WhatsApp não está conectado.');
    const result = await this.sock.sendMessage(this.normalizeJid(to), { text });
    return { id: result?.key.id ?? undefined };
  }

  /** Envia mídia a partir de base64 (mesmo contrato do MessageMedia do wwebjs). */
  async sendMediaBase64(
    to: string,
    base64: string,
    mimetype: string,
    filename?: string,
    caption?: string,
  ): Promise<{ id: string | undefined }> {
    if (!this.sock || !this.connected) throw new Error('WhatsApp não está conectado.');
    const buffer = Buffer.from(base64, 'base64');
    const jid = this.normalizeJid(to);

    let content: AnyMessageContent;
    if (mimetype.startsWith('image/')) {
      content = { image: buffer, caption: caption ?? undefined };
    } else if (mimetype.startsWith('video/')) {
      content = { video: buffer, caption: caption ?? undefined };
    } else if (mimetype.startsWith('audio/')) {
      content = { audio: buffer, mimetype, ptt: mimetype.includes('ogg') };
    } else {
      content = {
        document: buffer,
        mimetype,
        caption: caption ?? undefined,
        fileName: filename || 'arquivo',
      };
    }
    const result = await this.sock.sendMessage(jid, content);
    return { id: result?.key.id ?? undefined };
  }

  // ── Contatos / saúde ───────────────────────────────────

  /** JIDs de contatos 1:1 — formato equivalente ao getContacts() do wwebjs. */
  getJids(): string[] {
    if (!this.sock) return [];
    const store = (this.sock as unknown as { contacts?: Record<string, unknown> }).contacts;
    if (!store) return [];
    return Object.keys(store).filter(
      (jid) => jid.endsWith('@s.whatsapp.net'),
    );
  }

  /** Checagem leve de saúde — consulta o próprio estado do socket. */
  healthPing(): boolean {
    if (!this.sock || !this.connected) return false;
    try {
      const user = this.sock.user;
      return Boolean(user?.id);
    } catch {
      return false;
    }
  }

  /** Baixa o conteúdo de mídia de uma mensagem recebida (buffer). */
  async downloadMedia(msg: BaileysIncomingMessage & { raw?: unknown }): Promise<Buffer | null> {
    if (!this.sock) return null;
    const raw = msg.raw;
    if (!raw) return null;
    try {
      // Assinatura 6.7.x: downloadMediaMessage(msg, opts, ctx)
      const buf = await (downloadMediaMessage as unknown as (
        m: unknown, o: { reuploadRequest: WASocket['updateMediaMessage'] }, ctx: WASocket,
      ) => Promise<Buffer | unknown>)(
        raw,
        { reuploadRequest: this.sock.updateMediaMessage },
        this.sock,
      );
      return Buffer.isBuffer(buf) ? buf : null;
    } catch {
      return null;
    }
  }
}

/** Converte WAMessage para o formato que o incoming.ts já consome (wwebjs-like). */
export function toIncomingShape(msg: Parameters<Parameters<WASocket['ev']['on']>[1]>[0] extends never ? never : any): BaileysIncomingMessage & { raw: unknown } {
  const jid = msg.key.remoteJid ?? '';
  const type = Object.keys(msg.message ?? {})[0] ?? 'unknown';
  const m = msg.message as Record<string, Record<string, unknown> | undefined> | undefined;
  const body =
    (m?.conversation as string | undefined) ??
    (m?.extendedTextMessage?.text as string | undefined) ??
    (m?.imageMessage?.caption as string | undefined) ??
    (m?.videoMessage?.caption as string | undefined) ??
    (m?.documentMessage?.caption as string | undefined) ??
    '';
  return {
    id: msg.key.id ?? undefined,
    from: jid,
    fromMe: Boolean(msg.key.fromMe),
    // Em grupos o participante vem em participant — mantém a regra do incoming.ts
    author: jid.endsWith('@g.us') ? (msg.key.participant ?? undefined) : undefined,
    body,
    type,
    timestamp: Number(msg.messageTimestamp ?? 0),
    raw: msg,
  };
}
