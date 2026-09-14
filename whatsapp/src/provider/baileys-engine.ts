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
  type WAMessage,
  type UserFacingSocketConfig,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import pino from 'pino';
import { logger } from '../log';

/** Logger dedicado do Baileys (pino) — padrão da lib; silencioso por padrão. */
const baileysLogger = pino({ level: process.env.BAILEYS_LOG_LEVEL || 'error' });

const AUTH_DIR = process.env.BAILEYS_AUTH_DIR || path.join(process.cwd(), 'baileys_auth');

export type EngineEvent =
  | 'qr'
  | 'authenticated'
  | 'ready'
  | 'disconnected'
  | 'logged_out'
  | 'close'
  | 'message';

/** Payload do evento 'close' — telemetria do diagnóstico de loops (Fase 1/3). */
export interface CloseEventPayload {
  /** Status HTTP do Boom (401 logged_out, 408 timeout, 428 connection closed, 515 restart, 440 conflict). */
  statusCode: number | null;
  /** Razão bruta (String(statusCode) ou 'unknown') — mesmo valor do evento 'disconnected'. */
  reason: string;
  /** Classificação do erro pelo output.payload do Boom, quando disponível. */
  errorText: string;
}

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

/** Forma mínima dos eventos de contato do Baileys (Types/Contact). */
interface BaileysContact {
  id: string;
  jid?: string;
  name?: string;
  notify?: string;
  verifiedName?: string;
}

export class BaileysEngine {
  private sock: WASocket | null = null;  // exposto (leitura) p/ heartbeat do manager
  private connected = false;
  private qrString: string | null = null;
  private phone: string | null = null;
  private state: 'disconnected' | 'connecting' | 'qr_pending' | 'connected' = 'disconnected';
  private intentionallyStopped = false;
  /**
   * Catálogo de contatos 1:1 acumulado dos eventos (Baileys 6.7+ NÃO mantém
   * mais sock.contacts — contacts.upsert/update e messaging-history.set são
   * as fontes; messages.upsert complementa com pushName).
   */
  private readonly contactsStore = new Map<string, { name: string | null; pushName: string | null; verifiedName: string | null }>();
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
            logger.info('account.pairing_code_generated', { accountId: this.accountId, code });
          } catch (err) {
            logger.warn('account.pairing_code_failed', { accountId: this.accountId, error: err instanceof Error ? err.message : String(err) });
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
        const statusCode = (lastDisconnect?.error as Boom | undefined)?.output?.statusCode ?? null;
        const reason = statusCode !== null ? String(statusCode) : 'unknown';
        const errorText = String(
          (lastDisconnect?.error as Boom | undefined)?.output?.payload?.text ??
          (lastDisconnect?.error as Error | undefined)?.message ?? 'unknown',
        );
        const loggedOut = statusCode === DisconnectReason.loggedOut;

        if (this.intentionallyStopped) return;

        // Telemetria SEMPRE: todo close carrega statusCode/reason — sem isso o
        // próximo loop é indiagnóstico (lição do incidente de 408, 2026-09-06).
        onEvent('close', { statusCode, reason, errorText });

        if (loggedOut) {
          this.state = 'disconnected';
          // Evento distinto: manager apaga credenciais corrompidas e reabre QR.
          onEvent('logged_out');
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
        // Contatos aparecem também nas mensagens (pushName) — complementa o catálogo.
        const jid = msg.key.remoteJid;
        if (jid && jid.endsWith('@s.whatsapp.net')) {
          this.mergeContacts([{ id: jid, notify: msg.pushName ?? undefined }]);
        }
        onEvent('message', toIncomingShape(msg));
      }
    });

    // Catálogo de contatos (Baileys 6.7+): eventos em vez de sock.contacts.
    sock.ev.on('contacts.upsert', (cs) => this.mergeContacts(cs));
    sock.ev.on('contacts.update', (cs) => this.mergeContacts(cs));
    sock.ev.on('messaging-history.set', (payload) => {
      this.mergeContacts(payload.contacts ?? []);
      for (const chat of (payload.chats ?? []) as Array<{ id?: string; name?: string }>) {
        if (chat.id && chat.id.endsWith('@s.whatsapp.net')) {
          this.mergeContacts([{ id: chat.id, name: chat.name }]);
        }
      }
    });
  }

  /** Mescla contatos dos eventos no catálogo em memória (jid tem precedência sobre lid). */
  private mergeContacts(cs: Array<Partial<BaileysContact>>): void {
    for (const c of cs) {
      const jid = c.jid && c.jid.includes('@') ? c.jid : typeof c.id === 'string' && c.id.includes('@') ? c.id : null;
      if (!jid) continue;
      const prev = this.contactsStore.get(jid);
      this.contactsStore.set(jid, {
        name: c.name ?? prev?.name ?? null,
        pushName: c.notify ?? prev?.pushName ?? null,
        verifiedName: c.verifiedName ?? prev?.verifiedName ?? null,
      });
    }
  }

  /**
   * Encerra o socket SEM destruir listeners nem afetar a sessão em disco.
   *
   * Corrigido (incidente logged_out/recovery): antes este método chamava
   * removeAllListeners(), o que quebrava o fluxo já em andamento — o manager
   * aguardava eventos da instância antiga (ex.: conclusão do logout) enquanto
   * a nova subia. Quem zera `intentionallyStopped` e listeners é connect().
   */
  async disconnect(): Promise<void> {
    this.connected = false;
    this.state = 'disconnected';
    const sock = this.sock;
    this.sock = null;
    if (!sock) return;
    try {
      sock.end(new Error('intentional disconnect'));
    } catch { /* socket já fechado */ }
  }

  /**
   * Invalida a sessão no servidor (se houver socket vivo) e apaga TODAS as
   * credenciais locais (creds.json + chaves Signal). Ao contrário do
   * disconnect(), NÃO preserva nada — é o caminho do re-pareamento.
   *
   * Não exige socket vivo: num logged_out o socket normalmente já morreu;
   * o server-side logout (sock.logout()) é best-effort e a limpeza local
   * (fs.rmSync em baileys_auth/<accountId>/) é o efeito garantido.
   */
  async logout(): Promise<void> {
    const sock = this.sock;
    try {
      if (sock) await sock.logout();
    } catch { /* sessão pode já estar inválida ou socket morto — segue */ }
    await this.disconnect();
    try {
      fs.rmSync(path.join(AUTH_DIR, this.accountId), { recursive: true, force: true });
    } catch { /* ignore */ }
    this.phone = null;
    this.qrString = null;
    this.contactsStore.clear();
  }

  /**
   * Apaga APENAS a sessão Signal dessincronizada, preservando creds.json e
   * app-state (caminho B — erro 428 Bad MAC/No session record: o device é
   * válido no servidor, só as chaves de sessão locais corromperam).
   */
  async clearSignalSession(): Promise<void> {
    const sessionDir = path.join(AUTH_DIR, this.accountId);
    if (!fs.existsSync(sessionDir)) return;
    const removed: string[] = [];
    for (const name of fs.readdirSync(sessionDir)) {
      if (!SIGNAL_SESSION_PREFIXES.some((p) => name.startsWith(p))) continue;
      try {
        fs.rmSync(path.join(sessionDir, name), { recursive: true, force: true });
        removed.push(name);
      } catch { /* segue — arquivo pode estar travado pelo SO */ }
    }
    logger.warn('baileys.signal_session_cleared', {
      accountId: this.accountId,
      removedCount: removed.length,
    });
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
    const fromStore = Array.from(this.contactsStore.keys()).filter((jid) => jid.endsWith('@s.whatsapp.net'));
    if (fromStore.length > 0) return fromStore;
    // Fallback legado: versões antigas do Baileys mantinham sock.contacts.
    if (!this.sock) return [];
    const store = (this.sock as unknown as { contacts?: Record<string, unknown> }).contacts;
    if (!store) return [];
    return Object.keys(store).filter(
      (jid) => jid.endsWith('@s.whatsapp.net'),
    );
  }

  /** Catálogo com nomes — consumido pelo provider-manager (baileys branch). */
  getContactEntries(): Array<{ jid: string; phone: string | null; name: string | null; pushName: string | null; businessName: string | null }> {
    return this.getJids().map((jid) => {
      const e = this.contactsStore.get(jid);
      return {
        jid,
        phone: jid.split('@')[0] ?? null,
        name: e?.name ?? null,
        pushName: e?.pushName ?? null,
        businessName: e?.verifiedName ?? null,
      };
    });
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
export function toIncomingShape(msg: WAMessage): BaileysIncomingMessage & { raw: unknown } {
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

/** Caminho do auth dir (exposto p/ diagnóstico e testes). */
export function getAuthDir(): string {
  return AUTH_DIR;
}

/** Padrões de arquivo da sessão Signal (usado em clearSignalSession e testes). */
export const SIGNAL_SESSION_PREFIXES = ['session-', 'sender-key-', 'pre-key-'];
