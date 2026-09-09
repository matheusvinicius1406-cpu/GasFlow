import { test } from "node:test";
import assert from "node:assert/strict";
import { detectOrderTable } from "../src/detector";
import { parseMoney, parseQuantity, parseItemText, tableToOrders, extractPhone } from "../src/normalizer";
import { ORDERS_TABLE_HTML, MULTI_ITEM_HTML } from "./fixtures";

test("parseMoney entende pt-BR e formatos mistos", () => {
  assert.equal(parseMoney("R$ 1.234,56"), 1234.56);
  assert.equal(parseMoney("235,90"), 235.9);
  assert.equal(parseMoney("R$ 15.90"), 15.9);
  assert.equal(parseMoney(""), null);
  assert.equal(parseMoney(null), null);
});

test("parseQuantity lida com 2, x2 e lixo", () => {
  assert.equal(parseQuantity("2"), 2);
  assert.equal(parseQuantity("x3"), 3);
  assert.equal(parseQuantity("abc"), 1);
  assert.equal(parseQuantity("0"), 1);
});

test("parseItemText quebra '2x P13'", () => {
  const item = parseItemText("2x Botijão P13")!;
  assert.equal(item.quantity, 2);
  assert.equal(item.product_name, "Botijão P13");
});

test("extractPhone acha telefone BR", () => {
  assert.equal(extractPhone("(91) 98168-9969"), "(91) 98168-9969");
  assert.equal(extractPhone("sem fone"), "");
});

test("tableToOrders extrai pedidos e ignora linha vazia", () => {
  const table = detectOrderTable(ORDERS_TABLE_HTML)!;
  const { orders, errors } = tableToOrders(table);
  assert.equal(errors.length, 0);
  assert.equal(orders.length, 3);

  const first = orders[0];
  assert.equal(first.external_id, "1001");
  assert.equal(first.client_name, "Maria Souza");
  assert.equal(first.client_phone, "(91) 98168-9969");
  assert.equal(first.items.length, 1);
  assert.equal(first.items[0].product_name, "Botijão P13");
  assert.equal(first.items[0].quantity, 2);
  assert.equal(first.total, 220.0);
  assert.equal(first.status, "pendente");

  // Ana Costa sem telefone → client_phone vazio (backend gera placeholder único)
  const ana = orders[2];
  assert.equal(ana.client_name, "Ana Costa");
  assert.equal(ana.client_phone, "");
  assert.equal(ana.total, 300.0);
});

test("tableToOrders suporta múltiplos itens por célula", () => {
  const table = detectOrderTable(MULTI_ITEM_HTML)!;
  const { orders, errors } = tableToOrders(table);
  assert.equal(errors.length, 0);
  assert.equal(orders.length, 1);
  const order = orders[0];
  assert.equal(order.items.length, 2);
  assert.equal(order.items[0].product_name, "Botijão P13");
  assert.equal(order.items[0].quantity, 2);
  assert.equal(order.items[1].product_name, "Água 20L");
  assert.equal(order.address.includes("Rua das Flores"), true);
  assert.equal(order.total, 235.9);
});
