/**
 * Testes de deduplicação do upsert de contatos.
 * Usa um DATA_DIR temporário para não tocar no banco real (data/app.db).
 * IMPORTANTE: require() após a atribuição do DATA_DIR — import estático
 * seria içado e o db.ts leria o diretório errado.
 */
process.env.DATA_DIR = 'data/test-' + Date.now() + '-' + process.pid + '-' + Math.random().toString(36).slice(2, 8);

import assert from 'node:assert/strict';
import fs from 'node:fs';
import { after, test } from 'node:test';
import type { WhatsAppContact } from '../src/provider/types';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { closeDb, countContacts, getContactById } = require('../src/db');
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { mapToValues, upsertContacts } = require('../src/sync');

after(() => {
  // Fecha o SQLite antes de remover o diretório (senão dá EPERM no Windows).
  try {
    closeDb();
  } catch {
    // ignore
  }
  try {
    fs.rmSync(process.env.DATA_DIR as string, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  } catch {
    // diretório temporário remanescente é inofensivo
  }
});

/** Helper tipado para montar um contato de teste. */
function contact(overrides: Partial<WhatsAppContact> = {}): WhatsAppContact {
  return {
    jid: '5511999999999@c.us',
    phone: '5511999999999',
    name: 'Fulano',
    pushName: null,
    businessName: null,
    isBusiness: false,
    isGroup: false,
    ...overrides,
  };
}

test('upsert insere contato novo', () => {
  const result = upsertContacts([mapToValues(contact())]);
  assert.equal(result.inserted, 1);
  assert.equal(countContacts({}), 1);
});

test('sincronizar duas vezes NÃO cria duplicatas (dedupe por jid)', () => {
  const first = upsertContacts([mapToValues(contact())]);
  const second = upsertContacts([mapToValues(contact({ name: 'Fulano Atualizado' }))]);
  // O contato já existe dos testes anteriores: nada é inserido de novo.
  assert.equal(first.inserted + second.inserted, 0);
  assert.equal(second.updated, 1);
  assert.equal(countContacts({}), 1);

  const row = getContactById(1);
  assert.equal(row?.name, 'Fulano Atualizado');
});

test('mesmo telefone sob jid diferente reutiliza a linha (rebind)', () => {
  upsertContacts([mapToValues(contact())]);
  const result = upsertContacts([mapToValues(contact({ jid: '5511999999999@lid' }))]);
  assert.equal(result.inserted, 0);
  assert.equal(result.updated, 1);
  assert.equal(countContacts({}), 1);
  assert.equal(getContactById(1)?.jid, '5511999999999@lid');
});

test('telefones diferentes criam contatos separados', () => {
  upsertContacts([
    mapToValues(contact()),
    mapToValues(contact({ jid: '5522988888888@c.us', phone: '5522988888888', name: 'Beltrano' })),
  ]);
  assert.equal(countContacts({}), 2); // Fulano (existente) + Beltrano (novo)
});

test('grupos não recebem phone e são marcados como grupo', () => {
  const values = mapToValues(
    contact({
      jid: '12036301234567890@g.us',
      phone: null,
      name: 'Grupo Teste',
      isGroup: true,
    }),
  );
  assert.equal(values.phone, null);
  assert.equal(values.isGroup, 1);

  upsertContacts([values]);
  assert.equal(countContacts({ isGroup: 1 }), 1);
});
