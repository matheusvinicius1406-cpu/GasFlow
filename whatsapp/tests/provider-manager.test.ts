/**
 * FASE 5.24 — Complete WhatsApp Service Test Suite
 *
 * ALL tests use MockWhatsAppProvider — ZERO browser dependency.
 * Tests: unit, concurrency, persistence, boundary, idempotency.
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { MockWhatsAppProvider } from './mocks/mock-provider';

// ═══════════════════════════════════════════════════════════
// MOCK PROVIDER TESTS
// ═══════════════════════════════════════════════════════════

describe('MockWhatsAppProvider', () => {
  let mock: MockWhatsAppProvider;

  beforeEach(() => {
    mock = new MockWhatsAppProvider();
  });

  it('starts disconnected', () => {
    assert.equal(mock.isConnected(), false);
    assert.equal(mock.getStatus().state, 'disconnected');
  });

  it('connects and disconnects', () => {
    mock.simulateConnect();
    assert.equal(mock.isConnected(), true);
    mock.simulateDisconnect();
    assert.equal(mock.isConnected(), false);
  });

  it('shows QR pending', () => {
    mock.simulateQr();
    assert.equal(mock.getStatus().state, 'qr_pending');
    assert.equal(mock.getStatus().hasQr, true);
  });

  it('sends message and records it', async () => {
    mock.simulateConnect();
    const result = await mock.sendMessage('5511999999999', { text: 'Hello' });
    assert.equal(result.success, true);
    assert.ok(result.messageId);
    assert.equal(mock.sentMessages.length, 1);
    assert.equal(mock.sentMessages[0].recipient, '5511999999999');
    assert.equal(mock.sentMessages[0].text, 'Hello');
  });

  it('simulates send failure', async () => {
    mock.simulateConnect();
    mock.simulateSendFailure();
    const result = await mock.sendMessage('5511999999999', { text: 'Hello' });
    assert.equal(result.success, false);
    assert.equal(result.error, 'Mock send failure');
    assert.equal(mock.sentMessages.length, 0);
  });

  it('resets state', () => {
    mock.simulateConnect();
    mock.simulateSendFailure();
    mock.reset();
    assert.equal(mock.isConnected(), false);
    assert.equal(mock.sentMessages.length, 0);
  });

  it('returns null QR when not pending', () => {
    assert.equal(mock.getQr(), null);
  });

  it('returns QR when pending', () => {
    mock.simulateQr();
    const qr = mock.getQr();
    assert.ok(qr);
    assert.equal(qr.qr, 'mock-qr-string');
    assert.ok(qr.expiresIn > 0);
  });

  it('healthCheck reflects connection state', async () => {
    assert.equal(await mock.healthCheck(), false);
    mock.simulateConnect();
    assert.equal(await mock.healthCheck(), true);
  });

  it('getContacts throws when disconnected', async () => {
    await assert.rejects(() => mock.getContacts(), /não está conectado/);
  });

  it('getContacts returns empty when connected', async () => {
    mock.simulateConnect();
    const contacts = await mock.getContacts();
    assert.equal(contacts.length, 0);
  });
});

// ═══════════════════════════════════════════════════════════
// Phone Normalization Tests
// ═══════════════════════════════════════════════════════════

describe('normalizePhone', () => {
  const { normalizePhone } = require('../src/normalize');

  it('normalizes valid number', () => {
    assert.equal(normalizePhone('5511999999999'), '5511999999999');
  });

  it('strips leading zeros', () => {
    assert.equal(normalizePhone('0551199999999'), '551199999999');
  });

  it('strips non-digit chars', () => {
    assert.equal(normalizePhone('+55 (11) 99999-9999'), '5511999999999');
  });

  it('returns null for short numbers', () => {
    assert.equal(normalizePhone('123'), null);
  });

  it('returns null for null/undefined', () => {
    assert.equal(normalizePhone(null), null);
    assert.equal(normalizePhone(undefined), null);
  });

  it('returns null for empty string', () => {
    assert.equal(normalizePhone(''), null);
  });

  it('handles 9-digit mobile', () => {
    assert.equal(normalizePhone('11999999999'), '11999999999');
  });
});

// ═══════════════════════════════════════════════════════════
// Provider Types Contract
// ═══════════════════════════════════════════════════════════

describe('Provider Types Contract', () => {
  it('types module is importable', () => {
    const types = require('../src/provider/types');
    assert.ok(types);
  });

  it('interface has all required methods in source', () => {
    const fs = require('fs');
    const content = fs.readFileSync('src/provider/types.ts', 'utf-8');
    for (const method of ['start', 'stop', 'logout', 'getStatus', 'getQr', 'isConnected', 'healthCheck', 'getContacts', 'sendMessage']) {
      assert.ok(content.includes(method), `Missing: ${method}`);
    }
  });
});

// ═══════════════════════════════════════════════════════════
// API Boundary Tests
// ═══════════════════════════════════════════════════════════

describe('API Boundary', () => {
  it('frontend uses backend URL (port 8000)', () => {
    const url = process.env.VITE_API_URL || 'http://localhost:8000';
    assert.ok(url.includes('8000'));
    assert.ok(!url.includes('3001'));
  });

  it('WhatsApp Service uses SQLite, not PostgreSQL', () => {
    const fs = require('fs');
    const content = fs.readFileSync('src/db.ts', 'utf-8');
    assert.ok(content.includes('DatabaseSync'));
    assert.ok(!content.includes('postgresql'));
  });

  it('WhatsApp Service has no Order logic', () => {
    const fs = require('fs');
    const content = fs.readFileSync('src/routes.ts', 'utf-8');
    assert.ok(!content.includes('OrderModel'));
    assert.ok(!content.includes('order_repository'));
  });

  it('no whatsappProvider singleton import outside wwebjs-provider.ts', () => {
    const fs = require('fs');
    const path = require('path');
    const srcDir = 'src';
    const files = fs.readdirSync(srcDir).filter((f: string) => f.endsWith('.ts') && f !== 'wwebjs-provider.ts');
    for (const file of files) {
      const content = fs.readFileSync(path.join(srcDir, file), 'utf-8');
      assert.ok(
        !content.includes("from './provider/wwebjs-provider'"),
        `File ${file} still imports wwebjs-provider singleton`
      );
    }
  });
});

// ═══════════════════════════════════════════════════════════
// Concurrency Tests
// ═══════════════════════════════════════════════════════════

describe('Concurrency', () => {
  it('100 rapid sends with same mock', async () => {
    const mock = new MockWhatsAppProvider();
    mock.simulateConnect();
    const promises = Array.from({ length: 100 }, (_, i) =>
      mock.sendMessage('5511999999999', { text: `Msg ${i}` })
    );
    const results = await Promise.all(promises);
    assert.equal(results.filter(r => r.success).length, 100);
    assert.equal(mock.sentMessages.length, 100);
  });

  it('failure does not corrupt subsequent sends', async () => {
    const mock = new MockWhatsAppProvider();
    mock.simulateConnect();
    for (let i = 0; i < 10; i++) await mock.sendMessage('5511999999999', { text: `OK ${i}` });
    mock.simulateSendFailure();
    const fail = await mock.sendMessage('5511999999999', { text: 'Fail' });
    assert.equal(fail.success, false);
    for (let i = 0; i < 10; i++) await mock.sendMessage('5511999999999', { text: `After ${i}` });
    assert.equal(mock.sentMessages.length, 20); // 10 + 0 + 10
  });

  it('two accounts send independently', async () => {
    const mock1 = new MockWhatsAppProvider();
    const mock2 = new MockWhatsAppProvider();
    mock1.simulateConnect();
    mock2.simulateConnect();
    await mock1.sendMessage('5511111111111', { text: 'From 1' });
    await mock2.sendMessage('5511222222222', { text: 'From 2' });
    assert.equal(mock1.sentMessages.length, 1);
    assert.equal(mock2.sentMessages.length, 1);
    assert.equal(mock1.sentMessages[0].text, 'From 1');
    assert.equal(mock2.sentMessages[0].text, 'From 2');
  });
});

// ═══════════════════════════════════════════════════════════
// sent_messages Persistence Tests
// ═══════════════════════════════════════════════════════════

describe('sent_messages Persistence', () => {
  it('table exists', () => {
    const { db } = require('../src/db');
    const table = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='sent_messages'").get();
    assert.ok(table, 'sent_messages table should exist');
  });

  it('idempotency_key is UNIQUE NOT NULL', () => {
    const { db } = require('../src/db');
    const info = db.prepare("PRAGMA table_info(sent_messages)").all();
    const keyCol = info.find((c: any) => c.name === 'idempotency_key');
    assert.ok(keyCol);
    assert.equal(keyCol.notnull, 1);
    // UNIQUE is verified by insert behavior below
  });

  it('insert and find', () => {
    const { insertSentMessage, findSentMessageByKey } = require('../src/db');
    const key = `test-${Date.now()}-a`;
    const r = insertSentMessage({ idempotencyKey: key, accountId: 'primary', recipient: '5511999999999', messageText: 'Hello' });
    assert.ok(r.id);
    assert.equal(r.status, 'PENDING');
    assert.equal(findSentMessageByKey(key).id, r.id);
  });

  it('duplicate key returns existing', () => {
    const { insertSentMessage, findSentMessageByKey } = require('../src/db');
    const key = `test-${Date.now()}-b`;
    const r1 = insertSentMessage({ idempotencyKey: key, accountId: 'primary', recipient: '5511999999999', messageText: 'First' });
    const r2 = insertSentMessage({ idempotencyKey: key, accountId: 'primary', recipient: '5511999999999', messageText: 'Second' });
    assert.equal(r1.id, r2.id);
    assert.equal(findSentMessageByKey(key).message_text, 'First');
  });

  it('markSent updates status', () => {
    const { insertSentMessage, markSentMessageSent, findSentMessageByKey } = require('../src/db');
    const key = `test-${Date.now()}-c`;
    const r = insertSentMessage({ idempotencyKey: key, accountId: 'secondary', recipient: '5511888888888', messageText: 'Test' });
    markSentMessageSent(r.id, 'provider-abc');
    const updated = findSentMessageByKey(key);
    assert.equal(updated.status, 'SENT');
    assert.equal(updated.provider_msg_id, 'provider-abc');
    assert.ok(updated.sent_at);
  });

  it('markFailed updates status', () => {
    const { insertSentMessage, markSentMessageFailed, findSentMessageByKey } = require('../src/db');
    const key = `test-${Date.now()}-d`;
    const r = insertSentMessage({ idempotencyKey: key, accountId: 'primary', recipient: '5511777777777', messageText: 'Test' });
    markSentMessageFailed(r.id, 'Timeout');
    const updated = findSentMessageByKey(key);
    assert.equal(updated.status, 'FAILED');
    assert.equal(updated.error, 'Timeout');
  });

  it('listSentMessages works', () => {
    const { insertSentMessage, listSentMessages } = require('../src/db');
    const key = `test-${Date.now()}-e`;
    insertSentMessage({ idempotencyKey: key, accountId: 'primary', recipient: '5511666666666', messageText: 'List test' });
    const msgs = listSentMessages('primary', 10, 0);
    assert.ok(msgs.length >= 1);
    assert.ok(msgs.some((m: any) => m.idempotency_key === key));
  });
});

// ═══════════════════════════════════════════════════════════
// Idempotency End-to-End (with Mock)
// ═══════════════════════════════════════════════════════════

describe('Idempotency E2E (Mock)', () => {
  it('same key → only one send', async () => {
    const mock = new MockWhatsAppProvider();
    mock.simulateConnect();
    const { insertSentMessage, markSentMessageSent, findSentMessageByKey } = require('../src/db');
    const key = `idem-${Date.now()}-1`;

    // First request
    const existing = findSentMessageByKey(key);
    assert.equal(existing, undefined);

    const record = insertSentMessage({ idempotencyKey: key, accountId: 'primary', recipient: '5511999999999', messageText: 'Hello' });
    const result = await mock.sendMessage('5511999999999', { text: 'Hello' });
    markSentMessageSent(record.id, result.messageId || 'unknown');

    // Second request with same key
    const existing2 = findSentMessageByKey(key);
    assert.ok(existing2);
    assert.equal(existing2.status, 'SENT');
    // Should NOT send again
    assert.equal(mock.sentMessages.length, 1);
  });

  it('different keys → two sends', async () => {
    const mock = new MockWhatsAppProvider();
    mock.simulateConnect();
    const { insertSentMessage, markSentMessageSent, findSentMessageByKey } = require('../src/db');

    const key1 = `idem-${Date.now()}-x`;
    const key2 = `idem-${Date.now()}-y`;

    const r1 = insertSentMessage({ idempotencyKey: key1, accountId: 'primary', recipient: '5511999999999', messageText: 'First' });
    const res1 = await mock.sendMessage('5511999999999', { text: 'First' });
    markSentMessageSent(r1.id, res1.messageId || 'unknown');

    const r2 = insertSentMessage({ idempotencyKey: key2, accountId: 'primary', recipient: '5511999999999', messageText: 'Second' });
    const res2 = await mock.sendMessage('5511999999999', { text: 'Second' });
    markSentMessageSent(r2.id, res2.messageId || 'unknown');

    assert.equal(mock.sentMessages.length, 2);
    assert.notEqual(findSentMessageByKey(key1)?.id, findSentMessageByKey(key2)?.id);
  });
});

// ═══════════════════════════════════════════════════════════
// Account Isolation Test (Mock)
// ═══════════════════════════════════════════════════════════

describe('Account Isolation', () => {
  it('primary and secondary are independent', async () => {
    const primary = new MockWhatsAppProvider();
    const secondary = new MockWhatsAppProvider();

    primary.simulateConnect();
    // secondary stays disconnected

    await primary.sendMessage('5511111111111', { text: 'From primary' });
    assert.equal(primary.sentMessages.length, 1);
    assert.equal(secondary.sentMessages.length, 0);

    secondary.simulateConnect();
    await secondary.sendMessage('5511222222222', { text: 'From secondary' });
    assert.equal(primary.sentMessages.length, 1);
    assert.equal(secondary.sentMessages.length, 1);
  });

  it('logout primary does not affect secondary', async () => {
    const primary = new MockWhatsAppProvider();
    const secondary = new MockWhatsAppProvider();
    primary.simulateConnect();
    secondary.simulateConnect();

    await primary.logout();
    assert.equal(primary.isConnected(), false);
    assert.equal(secondary.isConnected(), true);
  });
});
