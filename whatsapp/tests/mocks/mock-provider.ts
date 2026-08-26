/**
 * MockWhatsAppProvider — Unit test mock that never starts a browser.
 *
 * Records sent messages for assertion.
 * Simulates connect/disconnect/QR states.
 */

import type {
  WhatsAppContact,
  WhatsAppProvider,
  WhatsAppQr,
  WhatsAppStatus,
  MessagePayload,
  SendResult,
} from '../../src/provider/types';

export interface MockSentMessage {
  recipient: string;
  text: string;
  timestamp: number;
  messageId: string;
}

export class MockWhatsAppProvider implements WhatsAppProvider {
  private connected = false;
  private hasQr = false;
  readonly sentMessages: MockSentMessage[] = [];
  private failNextSend = false;
  private messageCounter = 0;

  // ── State Control ──────────────────────────────────────

  simulateConnect(): void {
    this.connected = true;
    this.hasQr = false;
  }

  simulateDisconnect(): void {
    this.connected = false;
  }

  simulateQr(): void {
    this.hasQr = true;
    this.connected = false;
  }

  simulateSendFailure(): void {
    this.failNextSend = true;
  }

  reset(): void {
    this.connected = false;
    this.hasQr = false;
    this.sentMessages.length = 0;
    this.failNextSend = false;
    this.messageCounter = 0;
  }

  // ── WhatsAppProvider Interface ─────────────────────────

  start(): void {
    this.connected = false;
    this.hasQr = true;
  }

  async stop(): Promise<void> {
    this.connected = false;
    this.hasQr = false;
  }

  async logout(): Promise<void> {
    this.connected = false;
    this.hasQr = false;
  }

  getStatus(): WhatsAppStatus {
    return {
      state: this.connected ? 'connected' : this.hasQr ? 'qr_pending' : 'disconnected',
      connected: this.connected,
      hasQr: this.hasQr,
    };
  }

  getQr(): WhatsAppQr | null {
    if (!this.hasQr) return null;
    const now = Date.now();
    return {
      qr: 'mock-qr-string',
      generatedAt: new Date(now).toISOString(),
      expiresAt: new Date(now + 60000).toISOString(),
      expiresIn: 60,
    };
  }

  isConnected(): boolean {
    return this.connected;
  }

  async healthCheck(): Promise<boolean> {
    return this.connected;
  }

  async getContacts(): Promise<WhatsAppContact[]> {
    if (!this.connected) throw new Error('WhatsApp não está conectado.');
    return [];
  }

  async sendMessage(recipient: string, message: MessagePayload): Promise<SendResult> {
    if (this.failNextSend) {
      this.failNextSend = false;
      return { success: false, error: 'Mock send failure' };
    }

    this.messageCounter++;
    const messageId = `mock-msg-${this.messageCounter}-${Date.now()}`;

    this.sentMessages.push({
      recipient,
      text: message.text,
      timestamp: Date.now(),
      messageId,
    });

    return { success: true, messageId };
  }
}
