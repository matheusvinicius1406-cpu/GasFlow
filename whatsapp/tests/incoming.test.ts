/**
 * Incoming Message Bridge — unit tests.
 *
 * Cobre: mapeamento do payload, filtros (fromMe/grupo), retry, reply loopback
 * e cabeçalho de autenticação. Usa fetch e sendReply injetados — zero rede.
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { createIncomingForwarder, type RawIncomingMessage } from '../src/incoming';

interface CapturedRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

function makeFetch(handler: (req: CapturedRequest) => { status: number; body?: unknown }) {
  const calls: CapturedRequest[] = [];
  const fetchImpl = (async (url: string, init?: RequestInit) => {
    const parsed = JSON.parse(String(init?.body ?? '{}'));
    const call: CapturedRequest = {
      url: String(url),
      method: String(init?.method ?? 'GET'),
      headers: Object.fromEntries(
        Object.entries(init?.headers ?? {}).map(([k, v]) => [k, String(v)]),
      ),
      body: parsed,
    };
    calls.push(call);
    const res = handler(call);
    return {
      ok: res.status >= 200 && res.status < 300,
      status: res.status,
      json: async () => res.body ?? {},
    } as unknown as Response;
  }) as typeof fetch;
  return { fetchImpl, calls };
}

describe('IncomingForwarder', () => {
  const rawTextMessage: RawIncomingMessage = {
    id: { _serialized: 'WA-ID-123' },
    from: '5511987654321@c.us',
    fromMe: false,
    body: 'Quero um gás 13kg',
    type: 'chat',
    timestamp: 1_700_000_000,
  };

  it('encaminha mensagem recebida com payload correto', async () => {
    const { fetchImpl, calls } = makeFetch(() => ({ status: 200, body: { status: 'ok' } }));
    const forward = createIncomingForwarder({ backendUrl: 'http://backend:8000', serviceKey: '', fetchImpl });

    await forward('primary', rawTextMessage);

    assert.equal(calls.length, 1);
    const call = calls[0];
    assert.equal(call.url, 'http://backend:8000/whatsapp/incoming');
    assert.equal(call.method, 'POST');
    assert.deepEqual(call.body, {
      account_id: 'primary',
      sender_phone: '5511987654321',
      provider_message_id: 'WA-ID-123',
      text: 'Quero um gás 13kg',
      message_type: 'CHAT',
      from_me: false,
      timestamp: '2023-11-14T22:13:20.000Z',
    });
  });

  it('ignora mensagens enviadas por mim (fromMe)', async () => {
    const { fetchImpl, calls } = makeFetch(() => ({ status: 200 }));
    const forward = createIncomingForwarder({ backendUrl: 'http://backend:8000', serviceKey: '', fetchImpl });

    await forward('primary', { ...rawTextMessage, fromMe: true });
    assert.equal(calls.length, 0);
  });

  it('ignora mensagens de grupo (author presente)', async () => {
    const { fetchImpl, calls } = makeFetch(() => ({ status: 200 }));
    const forward = createIncomingForwarder({ backendUrl: 'http://backend:8000', serviceKey: '', fetchImpl });

    await forward('primary', { ...rawTextMessage, from: '5511999999999@g.us', author: '5511987654321@c.us' });
    assert.equal(calls.length, 0);
  });

  it('ignora mensagens sem remetente válido', async () => {
    const { fetchImpl, calls } = makeFetch(() => ({ status: 200 }));
    const forward = createIncomingForwarder({ backendUrl: 'http://backend:8000', serviceKey: '', fetchImpl });

    await forward('primary', { ...rawTextMessage, from: undefined });
    assert.equal(calls.length, 0);
  });

  it('não faz nada quando o bridge está desligado (sem backendUrl)', async () => {
    const { fetchImpl, calls } = makeFetch(() => ({ status: 200 }));
    const forward = createIncomingForwarder({ backendUrl: '', serviceKey: '', fetchImpl });

    await forward('primary', rawTextMessage);
    assert.equal(calls.length, 0);
  });

  it('envia o cabeçalho X-GasFlow-Key quando configurado', async () => {
    const { fetchImpl, calls } = makeFetch(() => ({ status: 200 }));
    const forward = createIncomingForwarder({ backendUrl: 'http://backend:8000', serviceKey: 'secret123', fetchImpl });

    await forward('primary', rawTextMessage);
    assert.equal(calls[0].headers['X-GasFlow-Key'], 'secret123');
  });

  it('responde automaticamente quando o backend devolve outbound_text', async () => {
    const { fetchImpl } = makeFetch(() => ({
      status: 200,
      body: { status: 'handled', outbound_text: 'Ok! Pedido registrado.', outbound_to: '5511987654321' },
    }));
    const replies: Array<{ account: string; to: string; text: string }> = [];
    const forward = createIncomingForwarder({
      backendUrl: 'http://backend:8000',
      serviceKey: '',
      fetchImpl,
      sendReply: async (account, to, text) => {
        replies.push({ account, to, text });
        return { success: true };
      },
    });

    await forward('primary', rawTextMessage);
    assert.deepEqual(replies, [{ account: 'primary', to: '5511987654321', text: 'Ok! Pedido registrado.' }]);
  });

  it('não envia resposta quando o backend não retorna outbound', async () => {
    const { fetchImpl } = makeFetch(() => ({ status: 200, body: { status: 'ignored' } }));
    let replyCalls = 0;
    const forward = createIncomingForwarder({
      backendUrl: 'http://backend:8000',
      serviceKey: '',
      fetchImpl,
      sendReply: async () => {
        replyCalls += 1;
        return { success: true };
      },
    });

    await forward('primary', rawTextMessage);
    assert.equal(replyCalls, 0);
  });

  it('tenta novamente em erro 5xx e tem sucesso na segunda tentativa', async () => {
    let attempt = 0;
    const { fetchImpl, calls } = makeFetch(() => {
      attempt += 1;
      return attempt === 1 ? { status: 503 } : { status: 200, body: { status: 'ok' } };
    });
    const forward = createIncomingForwarder({ backendUrl: 'http://backend:8000', serviceKey: '', fetchImpl, maxAttempts: 3 });

    await forward('primary', rawTextMessage);
    assert.equal(calls.length, 2);
  });

  it('não reenvia em erro 4xx (contrato/auth) — retry não ajuda', async () => {
    const { fetchImpl, calls } = makeFetch(() => ({ status: 401 }));
    const forward = createIncomingForwarder({ backendUrl: 'http://backend:8000', serviceKey: '', fetchImpl, maxAttempts: 3 });

    await forward('primary', rawTextMessage);
    assert.equal(calls.length, 1);
  });

  it('não lança exceção em falha de rede', async () => {
    const fetchImpl = (async () => {
      throw new Error('ECONNREFUSED');
    }) as typeof fetch;
    const forward = createIncomingForwarder({ backendUrl: 'http://backend:8000', serviceKey: '', fetchImpl });

    await assert.doesNotReject(() => forward('primary', rawTextMessage));
  });
});
