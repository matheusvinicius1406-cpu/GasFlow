import { db, addCustomerToList, getLists } from './db';

/**
 * Regras de população automática das listas de clientes do Marcos Gás.
 * Heurísticas por palavra-chave em name/push_name/business_name
 * dos contatos vinculados a customers.
 */
interface SeedRule {
  listName: string;
  where: string;
}

const SEED_RULES: SeedRule[] = [
  // Todos os clientes individuais (não grupos) entram na lista "Clientes".
  {
    listName: 'Clientes',
    where: 'c.is_group = 0',
  },
  {
    listName: 'Clientes Gás',
    where: `c.is_group = 0 AND (
      c.name LIKE '%gás%' COLLATE NOCASE OR c.push_name LIKE '%gás%' COLLATE NOCASE
      OR c.business_name LIKE '%gás%' COLLATE NOCASE OR c.name LIKE '%gas%' COLLATE NOCASE
      OR c.push_name LIKE '%gas%' COLLATE NOCASE OR c.business_name LIKE '%gas%' COLLATE NOCASE)`,
  },
  {
    listName: 'Clientes Água',
    where: `c.is_group = 0 AND (
      c.name LIKE '%água%' COLLATE NOCASE OR c.push_name LIKE '%água%' COLLATE NOCASE
      OR c.business_name LIKE '%água%' COLLATE NOCASE OR c.name LIKE '%agua%' COLLATE NOCASE
      OR c.push_name LIKE '%agua%' COLLATE NOCASE OR c.business_name LIKE '%agua%' COLLATE NOCASE
      OR c.name LIKE '%mineral%' COLLATE NOCASE OR c.push_name LIKE '%mineral%' COLLATE NOCASE
      OR c.business_name LIKE '%mineral%' COLLATE NOCASE)`,
  },
  {
    listName: 'Restaurantes',
    where: `c.is_group = 0 AND (
      c.name LIKE '%restaurante%' COLLATE NOCASE OR c.push_name LIKE '%restaurante%' COLLATE NOCASE
      OR c.business_name LIKE '%restaurante%' COLLATE NOCASE
      OR c.name LIKE '%pizzaria%' COLLATE NOCASE OR c.push_name LIKE '%pizzaria%' COLLATE NOCASE
      OR c.business_name LIKE '%pizzaria%' COLLATE NOCASE
      OR c.name LIKE '%lanchonete%' COLLATE NOCASE OR c.push_name LIKE '%lanchonete%' COLLATE NOCASE
      OR c.business_name LIKE '%lanchonete%' COLLATE NOCASE
      OR c.name LIKE '%burger%' COLLATE NOCASE OR c.push_name LIKE '%burger%' COLLATE NOCASE
      OR c.business_name LIKE '%burger%' COLLATE NOCASE
      OR c.name LIKE '%padaria%' COLLATE NOCASE OR c.push_name LIKE '%padaria%' COLLATE NOCASE
      OR c.business_name LIKE '%padaria%' COLLATE NOCASE
      OR c.name LIKE '%food%' COLLATE NOCASE OR c.push_name LIKE '%food%' COLLATE NOCASE
      OR c.business_name LIKE '%food%' COLLATE NOCASE)`,
  },
  {
    listName: 'Escolas',
    where: `c.is_group = 0 AND (
      c.name LIKE '%escola%' COLLATE NOCASE OR c.push_name LIKE '%escola%' COLLATE NOCASE
      OR c.business_name LIKE '%escola%' COLLATE NOCASE
      OR c.name LIKE '%colégio%' COLLATE NOCASE OR c.push_name LIKE '%colégio%' COLLATE NOCASE
      OR c.business_name LIKE '%colégio%' COLLATE NOCASE
      OR c.name LIKE '%colegio%' COLLATE NOCASE OR c.push_name LIKE '%colegio%' COLLATE NOCASE
      OR c.business_name LIKE '%colegio%' COLLATE NOCASE
      OR c.name LIKE '%creche%' COLLATE NOCASE OR c.push_name LIKE '%creche%' COLLATE NOCASE
      OR c.business_name LIKE '%creche%' COLLATE NOCASE
      OR c.name LIKE '%educac%' COLLATE NOCASE OR c.push_name LIKE '%educac%' COLLATE NOCASE
      OR c.business_name LIKE '%educac%' COLLATE NOCASE)`,
  },
  // Conta empresarial do WhatsApp ou com nome comercial definido.
  {
    listName: 'Empresas',
    where: 'c.is_group = 0 AND (c.is_business = 1 OR c.business_name IS NOT NULL)',
  },
];

export interface SeedResult {
  listName: string;
  listId: number;
  /** Clientes que bateram com a regra. */
  candidates: number;
  /** Membros efetivamente adicionados (idempotente). */
  added: number;
}

/** Idempotente: adiciona às listas os customers que casarem com cada regra. */
export function seedListsFromRules(): SeedResult[] {
  const byName = new Map(getLists().map((l) => [l.name, l.id]));
  const results: SeedResult[] = [];

  for (const rule of SEED_RULES) {
    const listId = byName.get(rule.listName);
    if (!listId) continue; // lista renomeada/removida pelo usuário — pula

    // Find customers whose linked contact matches the rule
    const candidates = db
      .prepare(
        `SELECT cu.id AS customer_id FROM customers cu
         JOIN contacts c ON c.id = cu.contact_id
         WHERE ${rule.where}`,
      )
      .all() as Array<{ customer_id: number }>;

    let added = 0;
    for (const c of candidates) {
      if (addCustomerToList(listId, c.customer_id)) added += 1;
    }
    results.push({ listName: rule.listName, listId, candidates: candidates.length, added });
  }
  return results;
}
