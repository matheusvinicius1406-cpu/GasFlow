/**
 * Mídia (sendMedia) — unit tests com MockWhatsAppProvider.
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { MockWhatsAppProvider } from './mocks/mock-provider';

describe('MockWhatsAppProvider.sendMedia', () => {
  let mock: MockWhatsAppProvider;

  beforeEach(() => {
    mock = new MockWhatsAppProvider();
  });

  it('falha quando desconectado', async () => {
    const result = await mock.sendMedia('5511999999999', { data: 'aGVsbG8=', mimetype: 'image/png' });
    assert.equal(result.success, false);
    assert.ok(result.error);
  });

  it('envia mídia e registra', async () => {
    mock.simulateConnect();
    const result = await mock.sendMedia('5511999999999', {
      data: 'aGVsbG8=',
      mimetype: 'image/png',
      filename: 'foto.png',
      caption: 'Olá!',
    });
    assert.equal(result.success, true);
    assert.ok(result.messageId);
    assert.equal(mock.sentMedia.length, 1);
    assert.equal(mock.sentMedia[0].recipient, '5511999999999');
    assert.equal(mock.sentMedia[0].media.mimetype, 'image/png');
    assert.equal(mock.sentMedia[0].media.caption, 'Olá!');
  });

  it('rejeita mídia sem data ou mimetype', async () => {
    mock.simulateConnect();
    const result = await mock.sendMedia('5511999999999', { data: '', mimetype: 'image/png' });
    assert.equal(result.success, false);
    assert.ok(result.error?.includes('obrigatórios'));
  });

  it('reporta falha quando o provider falha', async () => {
    mock.simulateConnect();
    mock.simulateSendFailure();
    const result = await mock.sendMedia('5511999999999', { data: 'aGVsbG8=', mimetype: 'audio/ogg' });
    assert.equal(result.success, false);
    assert.equal(result.error, 'Mock send failure');
    assert.equal(mock.sentMedia.length, 0);
  });
});
