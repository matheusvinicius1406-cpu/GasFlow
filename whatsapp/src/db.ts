import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';

const dataDir = process.env.DATA_DIR ?? path.join(process.cwd(), 'data');
fs.mkdirSync(dataDir, { recursive: true });

export const db = new DatabaseSync(path.join(dataDir, 'app.db'));
db.exec('PRAGMA journal_mode = WAL;');
db.exec('PRAGMA foreign_keys = ON;');
// Evita 'database is locked' quando há múltiplos acessos concorrentes.
db.exec('PRAGMA busy_timeout = 5000;');

db.exec(`
CREATE TABLE IF NOT EXISTS contacts (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  phone         TEXT,
  jid           TEXT NOT NULL UNIQUE,
  name          TEXT,
  push_name     TEXT,
  business_name TEXT,
  is_business   INTEGER NOT NULL DEFAULT 0,
  is_group      INTEGER NOT NULL DEFAULT 0,
  last_seen_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS lists (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS list_contacts (
  list_id    INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
  contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (list_id, contact_id)
);

CREATE TABLE IF NOT EXISTS list_members (
  list_id    INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (list_id, customer_id)
);
`);

// ---- Marcos Gás: clientes, preferências e campanhas ----
db.exec(`
CREATE TABLE IF NOT EXISTS customers (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  contact_id      INTEGER NOT NULL UNIQUE REFERENCES contacts(id) ON DELETE CASCADE,
  customer_status TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (customer_status IN ('CUSTOMER','PROSPECT','UNKNOWN')),
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS contact_preferences (
  customer_id     INTEGER PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
  marketing_status TEXT NOT NULL DEFAULT 'UNKNOWN'
    CHECK (marketing_status IN ('UNKNOWN','OPTED_IN','OPTED_OUT','SUPPRESSED','BLOCKED')),
  source          TEXT,
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS campaigns (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL,
  message      TEXT NOT NULL,
  list_id      INTEGER NOT NULL REFERENCES lists(id),
  status       TEXT NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT','RUNNING','PAUSED','CANCELLED','COMPLETED','FAILED')),
  protection   TEXT NOT NULL DEFAULT '{}' , -- JSON com motivo de PROTECTION_MODE
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  started_at   TEXT,
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS campaign_recipients (
  campaign_id         INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  customer_id         INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  status              TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','PROCESSING','SENT','FAILED','CANCELLED')),
  attempts            INTEGER NOT NULL DEFAULT 0,
  created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  started_at          TEXT,
  completed_at        TEXT,
  sent_at             TEXT,
  last_error          TEXT,
  lease_until         TEXT,
  error               TEXT,
  provider_message_id TEXT,
  PRIMARY KEY (campaign_id, customer_id) -- idempotência: campaign+customer único
);

-- Histórico de envios — base para rate limiting (janelas por conta) e
-- cooldown por destinatário. Indexes cobrem as duas consultas do limiter.
CREATE TABLE IF NOT EXISTS send_history (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id          TEXT NOT NULL,
  recipient           TEXT NOT NULL,
  sent_at_ms          INTEGER NOT NULL,
  provider_message_id TEXT,
  created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_send_history_account_time
  ON send_history (account_id, sent_at_ms);

CREATE INDEX IF NOT EXISTS idx_send_history_recipient
  ON send_history (account_id, recipient, sent_at_ms);

-- Contadores diários para warmup progressivo.
CREATE TABLE IF NOT EXISTS send_counters (
  account_id TEXT NOT NULL,
  day        TEXT NOT NULL,
  sent_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (account_id, day)
);

-- Migration: add new columns if they don't exist (safe for existing data)
CREATE TABLE IF NOT EXISTS _migration_tracking (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
`);

export interface ContactRow {
  id: number;
  phone: string | null;
  jid: string;
  name: string | null;
  push_name: string | null;
  business_name: string | null;
  is_business: number;
  is_group: number;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
}

export interface ListRow {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

// ---- Contacts ----

export function findContactByJid(jid: string): ContactRow | undefined {
  return db.prepare('SELECT * FROM contacts WHERE jid = ?').get(jid) as ContactRow | undefined;
}

export function findContactByPhone(phone: string): ContactRow | undefined {
  return db.prepare('SELECT * FROM contacts WHERE phone = ? AND phone IS NOT NULL').get(phone) as
    | ContactRow
    | undefined;
}

export function insertContact(values: {
  phone: string | null;
  jid: string;
  name: string | null;
  pushName: string | null;
  businessName: string | null;
  isBusiness: number;
  isGroup: number;
}): void {
  db.prepare(
    `INSERT INTO contacts (phone, jid, name, push_name, business_name, is_business, is_group, last_seen_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))`,
  ).run(values.phone, values.jid, values.name, values.pushName, values.businessName, values.isBusiness, values.isGroup);
}

export function updateContact(
  id: number,
  values: {
    phone: string | null;
    name: string | null;
    pushName: string | null;
    businessName: string | null;
    isBusiness: number;
    isGroup: number;
  },
): void {
  db.prepare(
    `UPDATE contacts
       SET phone = COALESCE(?, phone),
           name = ?,
           push_name = ?,
           business_name = ?,
           is_business = ?,
           is_group = ?,
           last_seen_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
           updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE id = ?`,
  ).run(values.phone, values.name, values.pushName, values.businessName, values.isBusiness, values.isGroup, id);
}

/** Re-points an existing record to a new jid (same phone seen under a different jid). */
export function rebindContactJid(jid: string, id: number): void {
  db.prepare("UPDATE contacts SET jid = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?").run(jid, id);
}

export function getContactById(id: number): ContactRow | undefined {
  return db.prepare('SELECT * FROM contacts WHERE id = ?').get(id) as ContactRow | undefined;
}

export interface ListContactsFilter {
  limit: number;
  offset: number;
  isGroup?: number;
  isBusiness?: number;
}

export function listContacts(filter: ListContactsFilter): ContactRow[] {
  return db
    .prepare(
      `SELECT * FROM contacts
       WHERE (? IS NULL OR is_group = ?)
         AND (? IS NULL OR is_business = ?)
       ORDER BY id
       LIMIT ? OFFSET ?`,
    )
    .all(
      filter.isGroup ?? null,
      filter.isGroup ?? null,
      filter.isBusiness ?? null,
      filter.isBusiness ?? null,
      filter.limit,
      filter.offset,
    ) as unknown as ContactRow[];
}

export function countContacts(filter: Pick<ListContactsFilter, 'isGroup' | 'isBusiness'>): number {
  const row = db
    .prepare(
      `SELECT COUNT(*) AS total FROM contacts
       WHERE (? IS NULL OR is_group = ?)
         AND (? IS NULL OR is_business = ?)`,
    )
    .get(filter.isGroup ?? null, filter.isGroup ?? null, filter.isBusiness ?? null, filter.isBusiness ?? null) as
    | { total: number }
    | undefined;
  return Number(row?.total ?? 0);
}

// ---- Lists ----

export function insertList(name: string, description: string | null): number {
  const result = db.prepare('INSERT INTO lists (name, description) VALUES (?, ?)').run(name, description);
  return Number(result.lastInsertRowid);
}

export function getLists(): ListRow[] {
  return db.prepare('SELECT * FROM lists ORDER BY id').all() as unknown as ListRow[];
}

export function getListById(id: number): ListRow | undefined {
  return db.prepare('SELECT * FROM lists WHERE id = ?').get(id) as ListRow | undefined;
}

export function renameList(id: number, name: string | null, description: string | null): void {
  db.prepare(
    `UPDATE lists
       SET name = COALESCE(?, name),
           description = COALESCE(?, description),
           updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE id = ?`,
  ).run(name, description, id);
}

export function deleteListById(id: number): boolean {
  return db.prepare('DELETE FROM lists WHERE id = ?').run(id).changes > 0;
}

export function countLists(): number {
  const row = db.prepare('SELECT COUNT(*) AS total FROM lists').get() as { total: number } | undefined;
  return Number(row?.total ?? 0);
}

// ---- List <-> Contact (legacy, kept for backward compat) ----

/** Idempotent: inserting an existing pair is a no-op. Returns true if inserted. */
export function addContactToList(listId: number, contactId: number): boolean {
  return (
    db
      .prepare('INSERT OR IGNORE INTO list_contacts (list_id, contact_id) VALUES (?, ?)')
      .run(listId, contactId).changes > 0
  );
}

export function removeContactFromList(listId: number, contactId: number): boolean {
  return db.prepare('DELETE FROM list_contacts WHERE list_id = ? AND contact_id = ?').run(listId, contactId).changes > 0;
}

export function getListContacts(listId: number): ContactRow[] {
  return db
    .prepare(
      `SELECT c.* FROM contacts c
       JOIN list_contacts lc ON lc.contact_id = c.id
       WHERE lc.list_id = ?
       ORDER BY c.id`,
    )
    .all(listId) as unknown as ContactRow[];
}

export function countListContacts(listId: number): number {
  const row = db.prepare('SELECT COUNT(*) AS total FROM list_contacts WHERE list_id = ?').get(listId) as
    | { total: number }
    | undefined;
  return Number(row?.total ?? 0);
}

// ---- List <-> Customer (list_members) ----

/** Idempotent: adds a customer to a list. Returns true if inserted. */
export function addCustomerToList(listId: number, customerId: number): boolean {
  return (
    db
      .prepare('INSERT OR IGNORE INTO list_members (list_id, customer_id) VALUES (?, ?)')
      .run(listId, customerId).changes > 0
  );
}

export function removeCustomerFromList(listId: number, customerId: number): boolean {
  return db.prepare('DELETE FROM list_members WHERE list_id = ? AND customer_id = ?').run(listId, customerId).changes > 0;
}

/** Returns customers in a list, joined with their contact info. */
export function getListCustomers(listId: number): Array<CustomerRow & { contact: ContactRow }> {
  const rows = db
    .prepare(
      `SELECT cu.id, cu.contact_id, cu.customer_status, cu.created_at, cu.updated_at,
              c.phone, c.jid, c.name, c.push_name, c.business_name, c.is_business, c.is_group, c.last_seen_at
       FROM customers cu
       JOIN contacts c ON c.id = cu.contact_id
       JOIN list_members lm ON lm.customer_id = cu.id
       WHERE lm.list_id = ?
       ORDER BY cu.id`,
    )
    .all(listId) as unknown as Array<Record<string, unknown>>;
  return rows.map(mapRowToCustomerWithContact);
}

export function countListCustomers(listId: number): number {
  const row = db.prepare('SELECT COUNT(*) AS total FROM list_members WHERE list_id = ?').get(listId) as
    | { total: number }
    | undefined;
  return Number(row?.total ?? 0);
}

/** Removes memberships pointing at contacts/customers/lists that no longer exist. */
export function cleanOrphanMemberships(): void {
  db.prepare(
    `DELETE FROM list_contacts
     WHERE contact_id NOT IN (SELECT id FROM contacts)
        OR list_id NOT IN (SELECT id FROM lists)`,
  ).run();
  db.prepare(
    `DELETE FROM list_members
     WHERE customer_id NOT IN (SELECT id FROM customers)
        OR list_id NOT IN (SELECT id FROM lists)`,
  ).run();
}

// ---- Deduplication ----

export interface DedupeResult {
  /** Linhas @lid removidas (identificador interno do WhatsApp, sem nome/telefone útil). */
  lidRemoved: number;
  /** Grupos de mesmo nome consolidados. */
  nameMergedGroups: number;
  /** Linhas removidas na consolidação por nome. */
  nameRemoved: number;
}

export interface RemovedDuplicate {
  id: number;
  name: string | null;
  phone: string | null;
  jid: string;
  keptId: number;
}

/**
 * Remove contatos com JID @lid: identificador interno do multi-device,
 * sem nome e cujo "user" NÃO é um número de telefone real.
 */
export function deleteLidContacts(): number {
  return Number(db.prepare("DELETE FROM contacts WHERE jid LIKE '%@lid'").run().changes);
}

/** Grupos de mesmo nome normalizado com mais de uma linha. */
export function findNameDuplicateGroups(): Array<{ nameKey: string; ids: number[] }> {
  const rows = db
    .prepare(
      `SELECT LOWER(TRIM(name)) AS name_key, id
       FROM contacts
       WHERE name IS NOT NULL AND TRIM(name) != ''
       ORDER BY LOWER(TRIM(name)), id`,
    )
    .all() as Array<{ name_key: string; id: number }>;

  const groups = new Map<string, number[]>();
  for (const r of rows) {
    const arr = groups.get(r.name_key) ?? [];
    arr.push(r.id);
    groups.set(r.name_key, arr);
  }
  return [...groups.entries()]
    .filter(([, ids]) => ids.length > 1)
    .map(([nameKey, ids]) => ({ nameKey, ids }));
}

/**
 * Consolida grupos de mesmo nome: mantém a linha mais antiga (menor id)
 * e remove as demais. As memberships das removidas migram para a mantida.
 * Retorna o que foi removido para auditoria do usuário.
 */
export function dedupeByName(): { result: DedupeResult['nameMergedGroups']; removed: RemovedDuplicate[] } {
  const removed: RemovedDuplicate[] = [];
  let mergedGroups = 0;

  db.exec('BEGIN IMMEDIATE');
  try {
    for (const group of findNameDuplicateGroups()) {
      const [keepId, ...dupeIds] = group.ids;
      mergedGroups += 1;
      for (const dupeId of dupeIds) {
        // Migra memberships da duplicata para a linha mantida (INSERT OR IGNORE evita conflito de PK).
        db.prepare(
          'INSERT OR IGNORE INTO list_contacts (list_id, contact_id) SELECT list_id, ? FROM list_contacts WHERE contact_id = ?',
        ).run(keepId, dupeId);

        const row = getContactById(dupeId);
        if (row) {
          removed.push({ id: row.id, name: row.name, phone: row.phone, jid: row.jid, keptId: keepId });
        }
        db.prepare('DELETE FROM contacts WHERE id = ?').run(dupeId);
      }
    }
    db.exec('COMMIT');
  } catch (err) {
    db.exec('ROLLBACK');
    throw err;
  }

  return { result: mergedGroups, removed };
}

// ---- Customers ----

export interface CustomerRow {
  id: number;
  contact_id: number;
  customer_status: string;
  created_at: string;
  updated_at: string;
}

export function getCustomerById(id: number): CustomerRow | undefined {
  return db.prepare('SELECT * FROM customers WHERE id = ?').get(id) as CustomerRow | undefined;
}

export function getCustomerByContactId(contactId: number): CustomerRow | undefined {
  return db.prepare('SELECT * FROM customers WHERE contact_id = ?').get(contactId) as CustomerRow | undefined;
}

export function insertCustomer(contactId: number, status: string = 'UNKNOWN'): number {
  const result = db
    .prepare('INSERT INTO customers (contact_id, customer_status) VALUES (?, ?)')
    .run(contactId, status);
  return Number(result.lastInsertRowid);
}

export function updateCustomerStatus(id: number, status: string): void {
  db.prepare(
    `UPDATE customers SET customer_status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?`,
  ).run(status, id);
}

export interface ListCustomersFilter {
  limit: number;
  offset: number;
  customerStatus?: string;
}

function mapRowToCustomerWithContact(row: Record<string, unknown>): CustomerRow & { contact: ContactRow } {
  const customer: CustomerRow = {
    id: Number(row.id),
    contact_id: Number(row.contact_id),
    customer_status: String(row.customer_status),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
  const contact: ContactRow = {
    id: Number(row.contact_id),
    phone: row.phone as string | null,
    jid: String(row.jid),
    name: row.name as string | null,
    push_name: row.push_name as string | null,
    business_name: row.business_name as string | null,
    is_business: Number(row.is_business),
    is_group: Number(row.is_group),
    last_seen_at: String(row.last_seen_at),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
  return { ...customer, contact };
}

export function listCustomers(filter: ListCustomersFilter): Array<CustomerRow & { contact: ContactRow }> {
  const rows = db
    .prepare(
      `SELECT cu.id, cu.contact_id, cu.customer_status, cu.created_at, cu.updated_at,
              c.phone, c.jid, c.name, c.push_name, c.business_name, c.is_business, c.is_group, c.last_seen_at
       FROM customers cu
       JOIN contacts c ON c.id = cu.contact_id
       WHERE (? IS NULL OR cu.customer_status = ?)
       ORDER BY cu.id
       LIMIT ? OFFSET ?`,
    )
    .all(filter.customerStatus ?? null, filter.customerStatus ?? null, filter.limit, filter.offset) as unknown as Array<Record<string, unknown>>;
  return rows.map(mapRowToCustomerWithContact);
}

export function countCustomers(filter: { customerStatus?: string } = {}): number {
  const row = db
    .prepare(
      `SELECT COUNT(*) AS total FROM customers
       WHERE (? IS NULL OR customer_status = ?)`,
    )
    .get(filter.customerStatus ?? null, filter.customerStatus ?? null) as { total: number } | undefined;
  return Number(row?.total ?? 0);
}

/** Promotes a contact to a customer (idempotent). Returns customer id. */
export function promoteContactToCustomer(contactId: number, status: string = 'UNKNOWN'): number {
  const existing = getCustomerByContactId(contactId);
  if (existing) return existing.id;
  return insertCustomer(contactId, status);
}

/** Get customer with full contact info. */
export function getCustomerWithContact(customerId: number): (CustomerRow & { contact: ContactRow }) | undefined {
  const row = db
    .prepare(
      `SELECT cu.id, cu.contact_id, cu.customer_status, cu.created_at, cu.updated_at,
              c.phone, c.jid, c.name, c.push_name, c.business_name, c.is_business, c.is_group, c.last_seen_at
       FROM customers cu
       JOIN contacts c ON c.id = cu.contact_id
       WHERE cu.id = ?`,
    )
    .get(customerId) as Record<string, unknown> | undefined;
  if (!row) return undefined;
  return mapRowToCustomerWithContact(row);
}

// ---- Contact Preferences ----

export interface ContactPreferenceRow {
  customer_id: number;
  marketing_status: string;
  source: string | null;
  updated_at: string;
}

export function getPreference(customerId: number): ContactPreferenceRow | undefined {
  return db.prepare('SELECT * FROM contact_preferences WHERE customer_id = ?').get(customerId) as
    | ContactPreferenceRow
    | undefined;
}

export function upsertPreference(customerId: number, marketingStatus: string, source: string | null = null): void {
  db.prepare(
    `INSERT INTO contact_preferences (customer_id, marketing_status, source, updated_at)
     VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
     ON CONFLICT(customer_id) DO UPDATE SET
       marketing_status = excluded.marketing_status,
       source = COALESCE(excluded.source, contact_preferences.source),
       updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')`,
  ).run(customerId, marketingStatus, source);
}

export function setOptOut(customerId: number, source: string = 'manual'): void {
  upsertPreference(customerId, 'OPTED_OUT', source);
}

export function setOptIn(customerId: number, source: string = 'manual'): void {
  upsertPreference(customerId, 'OPTED_IN', source);
}

/** Check if a customer is eligible for campaign communication. */
export function isCustomerEligible(customerId: number): boolean {
  const pref = getPreference(customerId);
  if (!pref) return true; // UNKNOWN = eligible by default
  return pref.marketing_status === 'UNKNOWN' || pref.marketing_status === 'OPTED_IN';
}

// ---- Campaigns ----

export interface CampaignRow {
  id: number;
  name: string;
  message: string;
  list_id: number;
  status: string;
  protection: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface CampaignRecipientRow {
  campaign_id: number;
  customer_id: number;
  status: string;
  attempts: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  sent_at: string | null;
  last_error: string | null;
  lease_until: string | null;
  error: string | null;
  provider_message_id: string | null;
}

export function insertCampaign(name: string, message: string, listId: number): number {
  const result = db
    .prepare('INSERT INTO campaigns (name, message, list_id) VALUES (?, ?, ?)')
    .run(name, message, listId);
  return Number(result.lastInsertRowid);
}

export function getCampaignById(id: number): CampaignRow | undefined {
  return db.prepare('SELECT * FROM campaigns WHERE id = ?').get(id) as CampaignRow | undefined;
}

export function listCampaigns(): CampaignRow[] {
  return db.prepare('SELECT * FROM campaigns ORDER BY id DESC').all() as unknown as CampaignRow[];
}

export function updateCampaignStatus(id: number, status: string): void {
  const now = "strftime('%Y-%m-%dT%H:%M:%fZ','now')";
  const updates: string[] = [`status = ?`, `started_at = COALESCE(started_at, ${now})`];
  const params: (string | number)[] = [status];

  if (status === 'COMPLETED' || status === 'FAILED' || status === 'CANCELLED') {
    updates.push(`completed_at = ${now}`);
  }
  if (status === 'RUNNING') {
    updates.push(`started_at = ${now}`);
  }

  db.prepare(`UPDATE campaigns SET ${updates.join(', ')} WHERE id = ?`).run(...params, id);
}

export function setCampaignProtection(id: number, reason: string): void {
  db.prepare(`UPDATE campaigns SET protection = ? WHERE id = ?`).run(JSON.stringify({ reason }), id);
}

/** Creates campaign recipients from a list's eligible customers (idempotent). */
export function createCampaignRecipients(campaignId: number, listId: number): {
  total: number;
  eligible: number;
  optedOut: number;
  blocked: number;
  duplicates: number;
} {
  // Get all customers in the list
  const customers = db
    .prepare(
      `SELECT cu.id AS customer_id, cu.contact_id FROM customers cu
       JOIN list_members lm ON lm.customer_id = cu.id
       WHERE lm.list_id = ?`,
    )
    .all(listId) as Array<{ customer_id: number; contact_id: number }>;

  let eligible = 0;
  let optedOut = 0;
  let blocked = 0;
  let duplicates = 0;

  const insertRecipient = db.prepare(
    `INSERT OR IGNORE INTO campaign_recipients (campaign_id, customer_id, status)
     VALUES (?, ?, 'PENDING')`,
  );

  for (const c of customers) {
    const pref = getPreference(c.customer_id);
    const status = pref?.marketing_status ?? 'UNKNOWN';

    if (status === 'OPTED_OUT' || status === 'SUPPRESSED') {
      optedOut++;
      // Record as excluded
      db.prepare(
        `INSERT OR IGNORE INTO campaign_recipients (campaign_id, customer_id, status, error)
         VALUES (?, ?, 'CANCELLED', ?)`,
      ).run(campaignId, c.customer_id, `Excluded: ${status}`);
      continue;
    }
    if (status === 'BLOCKED') {
      blocked++;
      db.prepare(
        `INSERT OR IGNORE INTO campaign_recipients (campaign_id, customer_id, status, error)
         VALUES (?, ?, 'CANCELLED', 'Excluded: BLOCKED')`,
      ).run(campaignId, c.customer_id);
      continue;
    }

    const result = insertRecipient.run(campaignId, c.customer_id);
    if (result.changes > 0) {
      eligible++;
    } else {
      duplicates++;
    }
  }

  return { total: customers.length, eligible, optedOut, blocked, duplicates };
}

export function getCampaignRecipients(campaignId: number): CampaignRecipientRow[] {
  return db
    .prepare('SELECT * FROM campaign_recipients WHERE campaign_id = ? ORDER BY customer_id')
    .all(campaignId) as unknown as CampaignRecipientRow[];
}

export function getCampaignResults(campaignId: number): {
  total: number;
  pending: number;
  processing: number;
  sent: number;
  failed: number;
  cancelled: number;
} {
  const row = db
    .prepare(
      `SELECT
         COUNT(*) AS total,
         SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending,
         SUM(CASE WHEN status = 'PROCESSING' THEN 1 ELSE 0 END) AS processing,
         SUM(CASE WHEN status = 'SENT' THEN 1 ELSE 0 END) AS sent,
         SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
         SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled
       FROM campaign_recipients WHERE campaign_id = ?`,
    )
    .get(campaignId) as Record<string, number> | undefined;
  return {
    total: Number(row?.total ?? 0),
    pending: Number(row?.pending ?? 0),
    processing: Number(row?.processing ?? 0),
    sent: Number(row?.sent ?? 0),
    failed: Number(row?.failed ?? 0),
    cancelled: Number(row?.cancelled ?? 0),
  };
}

/** Lease duration for a claimed job: 5 minutes. */
const LEASE_DURATION_MS = 5 * 60 * 1000;

/** Get next pending recipient for processing (atomic claim). */
export function claimNextRecipient(campaignId: number): CampaignRecipientRow | undefined {
  const row = db
    .prepare(
      `SELECT * FROM campaign_recipients
       WHERE campaign_id = ? AND status = 'PENDING'
       ORDER BY customer_id
       LIMIT 1`,
    )
    .get(campaignId) as CampaignRecipientRow | undefined;
  if (!row) return undefined;
  // Atomically mark as PROCESSING with lease
  const leaseUntil = new Date(Date.now() + LEASE_DURATION_MS).toISOString();
  const result = db
    .prepare(
      `UPDATE campaign_recipients
       SET status = 'PROCESSING',
           started_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
           attempts = attempts + 1,
           lease_until = ?
       WHERE campaign_id = ? AND customer_id = ? AND status = 'PENDING'`,
    )
    .run(leaseUntil, campaignId, row.customer_id);
  if (result.changes === 0) return undefined; // someone else claimed it
  return { ...row, status: 'PROCESSING', started_at: new Date().toISOString(), attempts: row.attempts + 1, lease_until: leaseUntil };
}

export function markRecipientSent(campaignId: number, customerId: number, providerMessageId: string): void {
  db.prepare(
    `UPDATE campaign_recipients
     SET status = 'SENT',
         sent_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
         completed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
         provider_message_id = ?
     WHERE campaign_id = ? AND customer_id = ?`,
  ).run(providerMessageId, campaignId, customerId);
}

export function markRecipientFailed(campaignId: number, customerId: number, error: string): void {
  db.prepare(
    `UPDATE campaign_recipients
     SET status = 'FAILED',
         completed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
         last_error = ?,
         error = ?
     WHERE campaign_id = ? AND customer_id = ?`,
  ).run(error, error, campaignId, customerId);
}

/** Recover stale PROCESSING jobs whose lease has expired. */
export function recoverStaleProcessing(): number {
  const result = db.prepare(
    `UPDATE campaign_recipients
     SET status = 'PENDING', lease_until = NULL, last_error = 'Lease expired — recovered on restart'
     WHERE status = 'PROCESSING'
       AND lease_until IS NOT NULL
       AND lease_until < strftime('%Y-%m-%dT%H:%M:%fZ','now')`,
  ).run();
  return Number(result.changes);
}

export function countPendingRecipients(campaignId: number): number {
  const row = db
    .prepare(
      `SELECT COUNT(*) AS total FROM campaign_recipients
       WHERE campaign_id = ? AND status = 'PENDING'`,
    )
    .get(campaignId) as { total: number } | undefined;
  return Number(row?.total ?? 0);
}

export function closeDb(): void {
  db.close();
}

// ---- FASE 5: Sent Messages (idempotency + audit) ----
db.exec(`
CREATE TABLE IF NOT EXISTS sent_messages (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key   TEXT NOT NULL UNIQUE,
  account_id        TEXT NOT NULL,
  recipient         TEXT NOT NULL,
  message_text      TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','SENT','FAILED')),
  provider_msg_id   TEXT,
  error             TEXT,
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  sent_at           TEXT
);

CREATE INDEX IF NOT EXISTS idx_sent_messages_idempotency
  ON sent_messages(idempotency_key);

CREATE INDEX IF NOT EXISTS idx_sent_messages_account
  ON sent_messages(account_id, created_at);
`);

// ---- FASE 5: Sent Messages Functions ----

export interface SentMessageRow {
  id: number;
  idempotency_key: string;
  account_id: string;
  recipient: string;
  message_text: string;
  status: string;
  provider_msg_id: string | null;
  error: string | null;
  created_at: string;
  sent_at: string | null;
}

/**
 * Check if a message with this idempotency key already exists.
 * Returns the existing row if found, undefined otherwise.
 */
export function findSentMessageByKey(idempotencyKey: string): SentMessageRow | undefined {
  return db.prepare('SELECT * FROM sent_messages WHERE idempotency_key = ?').get(idempotencyKey) as SentMessageRow | undefined;
}

/**
 * Insert a new sent message record (idempotent via UNIQUE constraint).
 * Returns the inserted row, or the existing row if key already exists.
 */
export function insertSentMessage(data: {
  idempotencyKey: string;
  accountId: string;
  recipient: string;
  messageText: string;
}): SentMessageRow {
  // Try to insert — UNIQUE constraint will reject duplicates
  try {
    db.prepare(
      `INSERT INTO sent_messages (idempotency_key, account_id, recipient, message_text)
       VALUES (?, ?, ?, ?)`
    ).run(data.idempotencyKey, data.accountId, data.recipient, data.messageText);
  } catch (err: unknown) {
    // UNIQUE constraint violation = duplicate key — return existing
    if (String(err).includes('UNIQUE')) {
      const existing = findSentMessageByKey(data.idempotencyKey);
      if (existing) return existing;
    }
    throw err;
  }
  return findSentMessageByKey(data.idempotencyKey)!;
}

/**
 * Mark a sent message as successfully sent.
 */
export function markSentMessageSent(id: number, providerMsgId: string): void {
  db.prepare(
    `UPDATE sent_messages
     SET status = 'SENT', provider_msg_id = ?, sent_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE id = ?`
  ).run(providerMsgId, id);
}

/**
 * Mark a sent message as failed.
 */
export function markSentMessageFailed(id: number, error: string): void {
  db.prepare(
    `UPDATE sent_messages
     SET status = 'FAILED', error = ?
     WHERE id = ?`
  ).run(error, id);
}

/**
 * List sent messages for an account (with pagination).
 */
export function listSentMessages(accountId: string, limit: number = 50, offset: number = 0): SentMessageRow[] {
  return db.prepare(
    `SELECT * FROM sent_messages
     WHERE account_id = ?
     ORDER BY created_at DESC
     LIMIT ? OFFSET ?`
  ).all(accountId, limit, offset) as unknown as SentMessageRow[];
}
