/**
 * Testes dos parsers puros do ai-service (dist/main/ai-service.js):
 * extractJsonBlock, parseMoney, coerceOrder, parseOrdersJson.
 * Sem electron nem fetch — só funções puras exportadas.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const req = createRequire(__filename);
// eslint-disable-next-line @typescript-eslint/no-var-requires
const {
  extractJsonBlock,
  parseMoney,
  coerceOrder,
  parseOrdersJson,
} = req("../dist/main/ai-service.js") as {
  extractJsonBlock: (raw: string) => string | null;
  parseMoney: (value: unknown) => number | null;
  coerceOrder: (raw: unknown, index: number) => { order?: unknown; error?: { message: string } };
  parseOrdersJson: (raw: string) => { orders: unknown[]; errors: { message: string }[] };
};

// ── extractJsonBlock ────────────────────────────────────

test("extractJsonBlock: objeto JSON simples", () => {
  const out = extractJsonBlock('{"orders":[]}');
  assert.equal(out, '{"orders":[]}');
});

test("extractJsonBlock: remove fence ```json", () => {
  const out = extractJsonBlock('```json\n{"orders":[]}\n```');
  assert.equal(out, '{"orders":[]}');
});

test("extractJsonBlock: extrai de texto com prefixo/sufixo", () => {
  const out = extractJsonBlock('Aqui está: {"a":1} espero que sirva');
  assert.equal(out, '{"a":1}');
});

test("extractJsonBlock: array balanceado", () => {
  const out = extractJsonBlock('[1,2,3]');
  assert.equal(out, '[1,2,3]');
});

test("extractJsonBlock: null quando não há JSON", () => {
  assert.equal(extractJsonBlock("só texto sem json"), null);
});

test("extractJsonBlock: balanceia strings com chaves internas", () => {
  const out = extractJsonBlock('{"nota":"tem } chave } dentro"}');
  assert.equal(out, '{"nota":"tem } chave } dentro"}');
});

// ── parseMoney ──────────────────────────────────────────

test("parseMoney: número finite passa direto", () => {
  assert.equal(parseMoney(42.5), 42.5);
});

test("parseMoney: NaN vira null", () => {
  assert.equal(parseMoney(Number.NaN), null);
});

test("parseMoney: null/undefined vira null", () => {
  assert.equal(parseMoney(null), null);
  assert.equal(parseMoney(undefined), null);
});

test("parseMoney: string pt-BR com vírgula decimal", () => {
  assert.equal(parseMoney("12,50"), 12.5);
});

test("parseMoney: string com milhar e decimal pt-BR", () => {
  assert.equal(parseMoney("1.234,56"), 1234.56);
});

test("parseMoney: string com ponto decimal (en-US)", () => {
  assert.equal(parseMoney("1234.56"), 1234.56);
});

test("parseMoney: remove símbolo de moeda", () => {
  assert.equal(parseMoney("R$ 89,90"), 89.9);
});

test("parseMoney: string vazia vira null", () => {
  assert.equal(parseMoney(""), null);
  assert.equal(parseMoney("   "), null);
});

test("parseMoney: texto não numérico vira null", () => {
  assert.equal(parseMoney("abc"), null);
});

// ── coerceOrder ─────────────────────────────────────────

test("coerceOrder: pedido válido com itens array", () => {
  const res = coerceOrder(
    {
      external_id: "PED-1",
      client_name: "João",
      items: [{ product_name: "Botijão 13kg", quantity: 2, unit_price: "89,90" }],
      total: "179,80",
    },
    0,
  );
  assert.ok(res.order, "não deve ter erro");
  const order = res.order as Record<string, unknown>;
  assert.equal(order.external_id, "PED-1");
  assert.equal(order.client_name, "João");
  const items = order.items as { product_name: string; quantity: number; unit_price: number }[];
  assert.equal(items.length, 1);
  assert.equal(items[0].product_name, "Botijão 13kg");
  assert.equal(items[0].quantity, 2);
  assert.equal(items[0].unit_price, 89.9);
  assert.equal(order.total, 179.8);
});

test("coerceOrder: aceita alias 'produto'/'quantidade'/'preco_unitario'", () => {
  const res = coerceOrder(
    { cliente: "Maria", produtos: [{ produto: "Água 20L", quantidade: 3, preco_unitario: 12 }] },
    0,
  );
  assert.ok(res.order);
  const order = res.order as Record<string, unknown>;
  assert.equal(order.client_name, "Maria");
  const items = order.items as { product_name: string; quantity: number; unit_price: number }[];
  assert.equal(items[0].product_name, "Água 20L");
  assert.equal(items[0].quantity, 3);
  assert.equal(items[0].unit_price, 12);
});

test("coerceOrder: gera external_id determinístico quando ausente", () => {
  const input = { client_name: "Ana", items: [{ product_name: "Botijão", quantity: 1 }] };
  const a = coerceOrder(input, 0) as { order: { external_id: string } };
  const b = coerceOrder(input, 0) as { order: { external_id: string } };
  assert.ok(a.order.external_id.startsWith("ai-"));
  assert.equal(a.order.external_id, b.order.external_id, "hash deve ser determinístico");
});

test("coerceOrder: sem itens retorna erro", () => {
  const res = coerceOrder({ external_id: "X", client_name: "Z" }, 3);
  assert.ok(res.error);
  assert.match(res.error!.message, /sem itens/);
});

test("coerceOrder: sem external_id nem client_name retorna erro", () => {
  const res = coerceOrder({ items: [{ product_name: "Água", quantity: 1 }] }, 5);
  assert.ok(res.error);
  assert.match(res.error!.message, /sem external_id nem client_name/);
});

test("coerceOrder: não-objeto retorna erro", () => {
  const res = coerceOrder("string solta", 0);
  assert.ok(res.error);
  assert.match(res.error!.message, /formato inesperado/);
});

// ── parseOrdersJson ─────────────────────────────────────

test("parseOrdersJson: objeto com orders válido", () => {
  const { orders, errors } = parseOrdersJson(
    '{"orders":[{"external_id":"1","client_name":"A","items":[{"product_name":"Gás","quantity":1}]}]}',
  );
  assert.equal(orders.length, 1);
  assert.equal(errors.length, 0);
});

test("parseOrdersJson: array direto também é aceito", () => {
  const { orders, errors } = parseOrdersJson(
    '[{"external_id":"2","client_name":"B","items":[{"product_name":"Água","quantity":2}]}]',
  );
  assert.equal(orders.length, 1);
  assert.equal(errors.length, 0);
});

test("parseOrdersJson: com fence ```json", () => {
  const { orders } = parseOrdersJson(
    '```json\n{"orders":[{"external_id":"3","client_name":"C","items":[{"product_name":"Gás","quantity":1}]}]}\n```',
  );
  assert.equal(orders.length, 1);
});

test("parseOrdersJson: entrada inválida gera erro", () => {
  const { orders, errors } = parseOrdersJson("não é json");
  assert.equal(orders.length, 0);
  assert.equal(errors.length, 1);
  assert.match(errors[0].message, /não devolveu JSON/);
});

test("parseOrdersJson: pedidos mistos (válidos + inválidos) separam orders/errors", () => {
  const raw = JSON.stringify({
    orders: [
      { external_id: "ok", client_name: "A", items: [{ product_name: "Gás", quantity: 1 }] },
      { external_id: "bad" }, // sem itens → erro
    ],
  });
  const { orders, errors } = parseOrdersJson(raw);
  assert.equal(orders.length, 1);
  assert.equal(errors.length, 1);
});
