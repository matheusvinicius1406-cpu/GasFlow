import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isGroupJid, jidUser, normalizePhone } from '../src/normalize';

test('normalizePhone: mantém apenas dígitos e remove zeros à esquerda', () => {
  assert.equal(normalizePhone('+55 (11) 99999-9999'), '5511999999999');
  assert.equal(normalizePhone('00551199999999'), '551199999999');
  assert.equal(normalizePhone('5511999999999'), '5511999999999');
});

test('normalizePhone: retorna null para entradas inválidas', () => {
  assert.equal(normalizePhone(null), null);
  assert.equal(normalizePhone(''), null);
  assert.equal(normalizePhone('abc'), null);
  assert.equal(normalizePhone('123'), null); // curto demais
});

test('jidUser: extrai a parte antes do @', () => {
  assert.equal(jidUser('5511999999999@c.us'), '5511999999999');
  assert.equal(jidUser('123abc@lid'), '123abc');
  assert.equal(jidUser('sem-arroba'), 'sem-arroba');
});

test('isGroupJid: identifica grupos e contatos individuais', () => {
  assert.equal(isGroupJid('120363@g.us'), true);
  assert.equal(isGroupJid('5511999999999@c.us'), false);
  assert.equal(isGroupJid('status@broadcast'), false);
});
