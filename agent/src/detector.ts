/**
 * Detector — identifica tabelas/listas de pedidos no HTML e infere o
 * mapeamento semântico das colunas (cliente, produto, valor, status...).
 *
 * Heurísticas: cabeçalhos de tabela com palavras-chave PT/EN; células com
 * "R$" → valor; "@" → e-mail; "kg"/códigos de botijão (P8/P13/P45) → produto.
 */

import { parse, HTMLElement } from "node-html-parser";
import type { IntegrationConfig } from "./types";

export type FieldKey =
  | "external_id"
  | "client_name"
  | "client_phone"
  | "client_email"
  | "address"
  | "product"
  | "quantity"
  | "unit_price"
  | "total"
  | "delivery_fee"
  | "payment_method"
  | "status"
  | "date"
  | "unknown";

export interface DetectedTable {
  headers: string[];
  headerIndex: number; // índice da linha de cabeçalho dentro de rows
  rows: string[][];
  mapping: Record<number, FieldKey>;
  score: number;
}

const HEADER_PATTERNS: Array<[RegExp, FieldKey]> = [
  [/^(n[ºo°]?|n[uú]mero|n[uú]m|pedido|order|c[oó]digo|id|#)\b/i, "external_id"],
  [/(cliente|client|customer|nome|consumidor)/i, "client_name"],
  [/(telefone|phone|celular|whatsa?pp|fone|contato)/i, "client_phone"],
  [/e-?mail/i, "client_email"],
  [/(endere[çc]o|address|rua|bairro|entrega)/i, "address"],
  [/(itens|items)/i, "product"],
  [/(produto|product|item|g[áa]s|botij[ãa]o|[áa]gua)/i, "product"],
  [/(quantid|qty|qtd|quantity)/i, "quantity"],
  [/(unit[áa]rio|unit.?price|pre[çc]o.?un)/i, "unit_price"],
  [/(total|valor|amount|pre[çc]o)/i, "total"],
  [/(frete|entrega|delivery|shipping)/i, "delivery_fee"],
  [/(pagamento|payment|forma)/i, "payment_method"],
  [/(status|situa[çc][ãa]o|estado)/i, "status"],
  [/(data|date|hor[áa]rio)/i, "date"],
];

export function classifyHeader(text: string): FieldKey {
  const clean = text.trim();
  if (!clean) return "unknown";
  for (const [re, key] of HEADER_PATTERNS) {
    if (re.test(clean)) return key;
  }
  return "unknown";
}

function cellText(el: HTMLElement): string {
  return (el.text ?? "").replace(/\s+/g, " ").trim();
}

/** Todas as linhas de uma tabela (células achatadas em texto). */
function extractTable(table: HTMLElement, rowSel: string, cellSel: string): { rows: string[][] } | null {
  const trs = table.querySelectorAll(rowSel);
  if (trs.length === 0) return null;
  const rows: string[][] = [];
  for (const tr of trs) {
    const cells = tr.querySelectorAll(cellSel);
    if (cells.length === 0) continue;
    rows.push(cells.map(cellText));
  }
  return rows.length ? { rows } : null;
}

/**
 * Tabelas candidatas: todas as <table> do HTML, ou as que casam com o
 * seletor configurado no painel. O seletor pode apontar para a própria
 * <table>, para um container que a contenha (div/section) ou para um
 * container de linhas sem <table> (lista em divs) — nesse caso quem acha as
 * linhas é o row selector.
 */
function resolveTables(root: HTMLElement, tableSel: string | null): HTMLElement[] {
  if (!tableSel) return root.querySelectorAll("table");
  const containers: HTMLElement[] = [];
  for (const el of root.querySelectorAll(tableSel)) {
    if (el.tagName?.toLowerCase() === "table") {
      containers.push(el);
      continue;
    }
    const inner = el.querySelectorAll("table");
    containers.push(inner.length > 0 ? inner[0] : el);
  }
  return containers;
}

function scoreHeaderRow(row: string[]): { score: number; mapping: Record<number, FieldKey> } {
  const mapping: Record<number, FieldKey> = {};
  let score = 0;
  row.forEach((cell, idx) => {
    const key = classifyHeader(cell);
    if (key !== "unknown") {
      mapping[idx] = key;
      score += 1;
    }
  });
  return { score, mapping };
}

/**
 * Detecta a melhor tabela de pedidos no HTML.
 *
 * selectors (painel) restringe onde procurar e como ler as linhas:
 *   { "table": "#pedidos", "row": "tr.pedido", "cell": "td" }
 * - table: seletor CSS da tabela (ou do container dela). Seletor que não casa
 *   com nada → null (falha explícita na sincronização, sem fallback). Quando
 *   configurado, o gate heurístico de score é relaxado: a escolha é do
 *   usuário (headers não-padrão são resolvidos via field_mapping).
 * - row/cell: seletores alternativos de linha/célula — permite layout em divs.
 */
export function detectOrderTable(
  html: string,
  selectors?: Record<string, string> | null
): DetectedTable | null {
  const root = parse(html);
  const tableSel = selectors?.table?.trim() || null;
  const rowSel = selectors?.row?.trim() || "tr";
  const cellSel = selectors?.cell?.trim() || "th, td";
  const tables = resolveTables(root, tableSel);
  // padrão: exige score ≥ 2 para não falsar tabela aleatória; com seletor
  // explícito, o usuário já apontou qual é a tabela de pedidos.
  const threshold = tableSel ? 0 : 2;
  let best: DetectedTable | null = null;

  for (const table of tables) {
    const extracted = extractTable(table, rowSel, cellSel);
    if (!extracted) continue;
    // procura a linha de cabeçalho com melhor score (até as 3 primeiras linhas)
    const scanLimit = Math.min(3, extracted.rows.length);
    for (let h = 0; h < scanLimit; h++) {
      const { score, mapping } = scoreHeaderRow(extracted.rows[h]);
      const hasIdAndClient = Object.values(mapping).includes("external_id") && Object.values(mapping).includes("client_name");
      const effective = score + (hasIdAndClient ? 2 : 0);
      if (effective >= threshold && (!best || effective > best.score)) {
        best = {
          headers: extracted.rows[h],
          headerIndex: h,
          rows: extracted.rows.slice(h + 1),
          mapping,
          score: effective,
        };
      }
    }
  }
  return best;
}

/**
 * Mapeamento declarativo (painel) sobrepõe a detecção:
 * field_mapping: { "client_name": "0", "total": "2", ... } — índice da coluna.
 */
export function applyConfiguredMapping(
  table: DetectedTable,
  fieldMapping: Record<string, string> | null | undefined
): DetectedTable {
  if (!fieldMapping || Object.keys(fieldMapping).length === 0) return table;
  const mapping: Record<number, FieldKey> = {};
  for (const [key, idxStr] of Object.entries(fieldMapping)) {
    const idx = Number.parseInt(idxStr, 10);
    if (!Number.isNaN(idx) && idx >= 0) mapping[idx] = key as FieldKey;
  }
  return Object.keys(mapping).length > 0 ? { ...table, mapping } : table;
}

export interface DetectedContext {
  html: string;
  table: DetectedTable | null;
  integration: IntegrationConfig;
}

export function detect(html: string, integration: IntegrationConfig): DetectedContext {
  const table = detectOrderTable(html, integration.selectors ?? null);
  if (!table) return { html, table: null, integration };
  const mapped = applyConfiguredMapping(table, integration.field_mapping);
  return { html, table: mapped, integration };
}
