/**
 * Contrato que isola o cliente WhatsApp da lógica de contatos/listas.
 * A implementação atual é o WhatsAppWebJsProvider (whatsapp-web.js);
 * trocar de provider (WPPConnect, Evolution, Baileys, Meta Cloud API)
 * não deve exigir mudanças em contatos/listas.
 */

export type WhatsAppConnectionState = 'disconnected' | 'connecting' | 'qr_pending' | 'connected';

export interface WhatsAppStatus {
  state: WhatsAppConnectionState;
  connected: boolean;
  hasQr: boolean;
}

/** Contato já normalizado pelo provider — formato único, independente da lib. */
export interface WhatsAppContact {
  jid: string;
  phone: string | null;
  name: string | null;
  pushName: string | null;
  businessName: string | null;
  isBusiness: boolean;
  isGroup: boolean;
}

export interface WhatsAppQr {
  /** Payload bruto do QR oficial do WhatsApp Web. */
  qr: string;
  generatedAt: string;
  expiresAt: string;
  expiresIn: number;
}

export interface SendResult {
  success: boolean;
  messageId?: string;
  error?: string;
}

export interface MessagePayload {
  text: string;
}

export interface WhatsAppProvider {
  start(): void;
  /** Encerra o cliente mantendo a sessão salva para o próximo boot. */
  stop(): Promise<void>;
  /** Invalida a sessão no servidor do WhatsApp e descarta credenciais locais. */
  logout(): Promise<void>;
  getStatus(): WhatsAppStatus;
  getQr(): WhatsAppQr | null;
  isConnected(): boolean;
  /**
   * Verificação leve de saúde com o servidor do WhatsApp
   * (padrão usado por WPPConnect/WAHA). Retorna false em qualquer falha.
   */
  healthCheck(): Promise<boolean>;
  getContacts(): Promise<WhatsAppContact[]>;
  sendMessage(recipient: string, message: MessagePayload): Promise<SendResult>;
}
