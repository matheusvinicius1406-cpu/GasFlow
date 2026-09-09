import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyHeader, detectOrderTable, applyConfiguredMapping } from "../src/detector";
import {
  ORDERS_TABLE_HTML,
  NO_TABLE_HTML,
  HEADED_ROW_HTML,
  SELECTOR_TABLE_HTML,
  DIV_LAYOUT_HTML,
} from "./fixtures";

test("classifyHeader mapeia cabeçalhos PT/EN", () => {
  assert.equal(classifyHeader("Cliente"), "client_name");
  assert.equal(classifyHeader("Pedido"), "external_id");
  assert.equal(classifyHeader("Nº"), "external_id");
  assert.equal(classifyHeader("Valor Total"), "total");
  assert.equal(classifyHeader("Quantidade"), "quantity");
  assert.equal(classifyHeader("Status"), "status");
  assert.equal(classifyHeader("Endereço"), "address");
  assert.equal(classifyHeader("Foo Bar"), "unknown");
});

test("detectOrderTable encontra a tabela de pedidos", () => {
  const table = detectOrderTable(ORDERS_TABLE_HTML);
  assert.ok(table, "tabela deveria ser detectada");
  const keys = Object.values(table.mapping);
  assert.ok(keys.includes("external_id"));
  assert.ok(keys.includes("client_name"));
  assert.ok(keys.includes("total"));
  assert.ok(table.rows.length >= 3);
});

test("detectOrderTable ignora página sem tabela", () => {
  assert.equal(detectOrderTable(NO_TABLE_HTML), null);
});

test("detectOrderTable acha cabeçalho não na primeira linha", () => {
  const table = detectOrderTable(HEADED_ROW_HTML);
  assert.ok(table, "tabela com header na 2ª linha deveria ser detectada");
  assert.equal(table.headers[0], "Pedido");
});

test("applyConfiguredMapping sobrepõe detecção", () => {
  const table = detectOrderTable(ORDERS_TABLE_HTML)!;
  const mapped = applyConfiguredMapping(table, { total: "1", client_name: "0" });
  assert.equal(mapped.mapping[1], "total");
  assert.equal(mapped.mapping[0], "client_name");
});

test("selectors.table restringe a busca à tabela configurada", () => {
  // sem seletor: a de histórico não pontua (headers sem match) e a #pedidos é detectada
  const semSeletor = detectOrderTable(SELECTOR_TABLE_HTML);
  assert.ok(semSeletor);
  assert.equal(semSeletor.headers[0], "Pedido");

  // com seletor: só a tabela apontada é considerada
  const comSeletor = detectOrderTable(SELECTOR_TABLE_HTML, { table: "#pedidos" });
  assert.ok(comSeletor, "tabela #pedidos deveria ser detectada");
  assert.equal(comSeletor.headers[0], "Pedido");
  assert.equal(comSeletor.rows.length, 1);
  assert.equal(comSeletor.rows[0][0], "4001");

  // seletor apontando para outra tabela: muda o alvo mesmo sendo "pior"
  const historico = detectOrderTable(SELECTOR_TABLE_HTML, { table: ".histórico" });
  assert.ok(historico, "tabela .histórico deveria ser detectada");
  assert.equal(historico.headers[0], "Protocolo");
  assert.equal(historico.rows[0][0], "900");
});

test("selectors.table aceita container que envolve a tabela", () => {
  const html = `<html><body><section id="painel">${ORDERS_TABLE_HTML.match(/<table[\s\S]*<\/table>/)?.[0] ?? ""}</section></body></html>`;
  const table = detectOrderTable(html, { table: "#painel" });
  assert.ok(table, "tabela dentro do container deveria ser detectada");
  assert.equal(table.headers[0], "Pedido");
});

test("selectors.table sem match → null (falha explícita, sem fallback)", () => {
  assert.equal(detectOrderTable(SELECTOR_TABLE_HTML, { table: "#inexistente" }), null);
});

test("selectors.row/cell suportam layout em divs", () => {
  const table = detectOrderTable(DIV_LAYOUT_HTML, {
    table: ".orders",
    row: "div.order-row",
    cell: "span.c",
  });
  assert.ok(table, "layout em divs deveria ser detectado");
  assert.equal(table.headers[0], "Pedido");
  assert.ok(table.rows.length === 2);
  assert.equal(table.rows[0][0], "5001");
  assert.equal(table.rows[1][2], "R$ 77,00");
});

test("selectors vazios/blank caem no comportamento padrão", () => {
  const table = detectOrderTable(ORDERS_TABLE_HTML, { table: "  ", row: "", cell: "   " });
  assert.ok(table, "selectors em branco deveriam ser ignorados");
  assert.equal(table.headers[0], "Pedido");
});
