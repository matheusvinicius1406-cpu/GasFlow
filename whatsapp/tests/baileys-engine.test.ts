/**
 * Baileys Engine — unit tests (sem conexão real).
 *
 * Cobre: normalização de JID, fail-closed quando desconectado, getters,
 * mapeamento de mensagens recebidas (wwebjs-like) e contatos.
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { BaileysEngine, toIncomingShape } from '../src/provider/baileys-engine';

describe('BaileysEngine (sem conexão)', () => {
  let engine: BaileysEngine;

  beforeEach(() => {
    engine = new BaileysEngine({ accountId: 'test-account' });
  });

  it('inicia desconectado e sem QR', () => {
    assert.equal(engine.isConnected, false);
    assert.equal(engine.stateName, 'disconnected');
    assert.equal(engine.qr, null);
    assert.equal(engine.phoneNumber, null);
  });

  it('normaliza JIDs — número puro vira @s.whatsapp.net', () => {
    assert.equal(engine.normalizeJid('5511999999999'), '5511999999999@s.whatsapp.net');
  });

  it('preserva JIDs que já contêm @', () => {
    assert.equal(engine.normalizeJid('5511999999999@s.whatsapp.net'), '5511999999999@s.whatsapp.net');
    assert.equal(engine.normalizeJid('grupo@g.us'), 'grupo@g.us');
  });

  it('sendText falha (fail-closed) sem conexão', async () => {
    await assert.rejects(() => engine.sendText('5511999999999', 'oi'), /não está conectado/);
  });

  it('sendMediaBase64 falha (fail-closed) sem conexão', async () => {
    await assert.rejects(
      () => engine.sendMediaBase64('5511999999999', 'aGVsbG8=', 'image/png'),
      /não está conectado/,
    );
  });

  it('healthPing retorna false sem socket', () => {
    assert.equal(engine.healthPing(), false);
  });

  it('getJids retorna lista vazia sem socket', () => {
    assert.deepEqual(engine.getJids(), []);
  });
});

// ── toIncomingShape — compatibilidade com incoming.ts ────

describe('toIncomingShape (wwebjs-like)', () => {
  it('mapeia mensagem de texto simples', () => {
    const shaped = toIncomingShape({
      key: { remoteJid: '5511999999999@s.whatsapp.net', fromMe: false, id: 'ABC123' },
      message: { conversation: 'Olá, tem gás?' },
      messageTimestamp: 1700000000,
      pushName: 'João',
    });
    assert.equal(shaped.id, 'ABC123');
    assert.equal(shaped.from, '5511999999999@s.whatsapp.net');
    assert.equal(shaped.fromMe, false);
    assert.equal(shaped.body, 'Olá, tem gás?');
    assert.equal(shaped.type, 'conversation');
    assert.equal(shaped.author, undefined);
    assert.ok(shaped.timestamp);
  });

  it('mapeia mensagem de grupo com author (participant)', () => {
    const shaped = toIncomingShape({
      key: {
        remoteJid: '120363@g.us',
        fromMe: false,
        id: 'G1',
        participant: '5511888888888@s.whatsapp.net',
      },
      message: { conversation: 'mensagem no grupo' },
      messageTimestamp: 1700000000,
    });
    assert.equal(shaped.author, '5511888888888@s.whatsapp.net');
  });

  it('1:1 não tem author (regra do incoming.ts ignora grupos por author)', () => {
    const shaped = toIncomingShape({
      key: { remoteJid: '5511999999999@s.whatsapp.net', fromMe: false, id: 'D1' },
      message: { extendedTextMessage: { text: 'resposta' } },
      messageTimestamp: 1700000000,
    });
    assert.equal(shaped.author, undefined);
    assert.equal(shaped.body, 'resposta');
    assert.equal(shaped.type, 'extendedTextMessage');
  });

  it('extrai caption de imagem', () => {
    const shaped = toIncomingShape({
      key: { remoteJid: '5511999999999@s.whatsapp.net', fromMe: true, id: 'P1' },
      message: { imageMessage: { caption: 'comprovante' } },
      messageTimestamp: 1700000000,
    });
    assert.equal(shaped.fromMe, true);
    assert.equal(shaped.body, 'comprovante');
    assert.equal(shaped.type, 'imageMessage');
  });

  it('mensagem sem corpo fica com string vazia (não quebra o bridge)', () => {
    const shaped = toIncomingShape({
      key: { remoteJid: '5511999999999@s.whatsapp.net', fromMe: false, id: 'E1' },
      message: { protocolMessage: { type: 3 } },
      messageTimestamp: 1700000000,
    });
    assert.equal(shaped.body, '');
  });

  it('timestamp numérico é propagado', () => {
    const shaped = toIncomingShape({
      key: { remoteJid: 'x@s.whatsapp.net', fromMe: false, id: 'T1' },
      message: { conversation: 'x' },
      messageTimestamp: 1700000123,
    });
    assert.equal(shaped.timestamp, 1700000123);
  });
});
