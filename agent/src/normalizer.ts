/**
 * Normalizer — linhas detectadas → NormalizedOrder (formato do backend).
 *
 * Sólido contra ruído de sites reais: moeda pt-BR, quantidade "2x", clientes
 * sem telefone, pedidos sem itens (gera erro controlado, não exceção).
 */

import type { DetectedTable, FieldKey } from "./detector";
import type { AgentError, NormalizedOrder, RawItem } from "./types";

export function parseMoney(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return value;
  let text = String(value).trim();
  if (!text) return null;
  text = text.replace(/[^\d,.]/g, "");
  if (!text) return null;
  if (text.includes(",") && text.includes(".")) {
    if (text.lastIndexOf(",") > text.lastIndexOf(".")) {
      text = text.replace(/\./g, "").replace(",", ".");
    } else {
      text = text.replace(/,/g, "");
    }
  } else if (text.includes(",")) {
    text = text.replace(",", ".");
  }
  const n = Number.parseFloat(text);
  return Number.isFinite(n) ? n : null;
}

export function parseQuantity(value: unknown): number {
  if (typeof value === "number") return value > 0 ? Math.floor(value) : 1;
  const text = String(value ?? "").trim();
  // "2", "2x", "x3", "2 x"
  const m = text.match(/^[xX×]?\s*(\d+(?:[.,]\d+)?)\s*[xX×]?\s*$/);
  if (m) {
    const n = Math.floor(Number.parseFloat(m[1].replace(",", ".")));
    return n > 0 ? n : 1;
  }
  return 1;
}

const BR_PHONE = /(\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4})/;

export function extractPhone(text: string): string {
  const m = text.match(BR_PHONE);
  return m ? m[1].trim() : "";
}

/** "2x P13" → { quantity: 2, product_name: "P13" } */
export function parseItemText(text: string): RawItem | null {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return null;
  const m = clean.match(/^(\d+(?:[.,]\d+)?)\s*[xX×]\s*(.+)$/);
  if (m) {
    return { product_name: m[2].trim(), quantity: parseQuantity(m[1]) };
  }
  return { product_name: clean, quantity: 1 };
}

function rowValue(row: string[], idx: number | undefined): string {
  if (idx === undefined || idx < 0 || idx >= row.length) return "";
  return (row[idx] ?? "").trim();
}

export function rowToOrder(
  row: string[],
  table: DetectedTable
): { order?: NormalizedOrder; error?: AgentError } {
  const byKey = new Map<FieldKey, string>();
  for (const [idxStr, key] of Object.entries(table.mapping)) {
    const idx = Number.parseInt(idxStr, 10);
    byKey.set(key, rowValue(row, idx));
  }

  const externalId = byKey.get("external_id") ?? "";
  const clientName = byKey.get("client_name") ?? "";
  if (!externalId && !clientName) {
    return { error: { external_ref: undefined, message: `Linha sem ID nem cliente: "${row.join(" | ").slice(0, 120)}"` } };
  }

  const items: RawItem[] = [];
  const productCell = byKey.get("product");
  if (productCell) {
    // pode conter múltiplos itens separados por ; ou newline
    const parts = productCell.split(/[;\n]+/).map((p) => p.trim()).filter(Boolean);
    for (const part of parts) {
      const item = parseItemText(part);
      if (item) items.push(item);
    }
  }
  const qtyCell = byKey.get("quantity");
  if (items.length > 0 && qtyCell) {
    const qty = parseQuantity(qtyCell);
    // se a célula de quantidade se refere a um único item, aplica
    if (items.length === 1 && qty > 1 && items[0].quantity === 1) {
      items[0].quantity = qty;
    }
  }

  if (items.length === 0) {
    return {
      error: {
        external_ref: externalId || undefined,
        message: `Pedido sem produtos reconhecíveis: "${row.join(" | ").slice(0, 120)}"`,
      },
    };
  }

  const addressCell = byKey.get("address") ?? "";
  const phoneCell = byKey.get("client_phone") ?? "";
  const emailCell = byKey.get("client_email") ?? "";

  const order: NormalizedOrder = {
    external_id: externalId || `row-${Math.abs(hash(row.join("|")))}`,
    client_name: clientName || "",
    client_phone: extractPhone(phoneCell),
    client_email: emailCell.includes("@") ? emailCell : "",
    address: addressCell,
    items,
    total: parseMoney(byKey.get("total")),
    delivery_fee: parseMoney(byKey.get("delivery_fee")),
    payment_method: byKey.get("payment_method") || null,
    status: byKey.get("status") ?? "",
    notes: "importado do site via agente GasFlow",
  };
  return { order };
}

/** Converte a tabela inteira em pedidos + erros. */
export function tableToOrders(table: DetectedTable): { orders: NormalizedOrder[]; errors: AgentError[] } {
  const orders: NormalizedOrder[] = [];
  const errors: AgentError[] = [];
  for (const row of table.rows) {
    if (row.every((c) => !c)) continue;
    const result = rowToOrder(row, table);
    if (result.order) orders.push(result.order);
    else if (result.error) errors.push(result.error);
  }
  return { orders, errors };
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  }
  return h;
}
