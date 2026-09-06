/**
 * Metrics — unit tests (prom-client).
 *
 * Cobre: renderização no formato Prometheus e incremento dos contadores.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  renderMetrics,
  messagesSentTotal,
  messagesFailedTotal,
  accountConnected,
  reconnectAttemptsTotal,
} from '../src/metrics';

describe('metrics', () => {
  it('renderiza texto no formato Prometheus', async () => {
    messagesSentTotal.inc({ account: 'primary' });
    messagesFailedTotal.inc({ account: 'primary', reason: 'send_error' });
    accountConnected.set({ account: 'primary', engine: 'baileys' }, 1);
    reconnectAttemptsTotal.inc({ account: 'secondary' });

    const text = await renderMetrics();
    assert.ok(text.includes('whatsapp_messages_sent_total'));
    assert.ok(text.includes('whatsapp_messages_failed_total'));
    assert.ok(text.includes('whatsapp_account_connected'));
    assert.ok(text.includes('whatsapp_reconnect_attempts_total'));
    // Default process metrics também presentes
    assert.ok(text.includes('process_cpu'));
  });

  it('labels são propagados nas séries', async () => {
    messagesSentTotal.inc({ account: 'metrics-test' });
    const text = await renderMetrics();
    const line = text
      .split('\n')
      .find((l) => l.startsWith('whatsapp_messages_sent_total') && l.includes('metrics-test'));
    assert.ok(line, 'série com label account=metrics-test não encontrada');
  });
});
