/**
 * queuePersistence — torna a fila offline do entregador sobrevivente ao
 * fechamento do app (prompt 3.1/5.4: "o estado offline não pode depender de
 * uma variável em memória que desapareça ao fechar o app").
 *
 * Camadas:
 * - `QueueStorage` (síncrono) é o contrato que o `OfflineQueue` já consome:
 *   a fila continua sendo lida/escrita de forma síncrona pela UI.
 * - O snapshot é espelhado em um KV **assíncrono** (`AsyncKV`) a cada
 *   mutação, em série (uma escrita por vez, sem corrida entre `save`/`remove`).
 * - `hydrate()` relê o snapshot no boot e faz merge com o que já estiver em
 *   memória, sem nunca ressuscitar ação já confirmada (`synced`).
 *
 * Módulo puro: nenhum import de React Native. O adapter real (AsyncStorage)
 * recebe o módulo já resolvido, exatamente como `tokenStorage.ts` faz com o
 * Keychain — o teste em node injeta um KV em memória com o mesmo contrato.
 */

import type { QueueItem, QueueOwner, QueueStorage } from "./offlineQueue.ts";
import { ownerMatches } from "./offlineQueue.ts";

/** Chave única do snapshot no KV (versão do esquema no próprio nome da chave). */
export const QUEUE_STORAGE_KEY = "gasflow.driver.queue.v1";

/**
 * Versão do payload. Mudança de formato ⇒ trocar a chave (`.v2`) e migrar na
 * `hydrate()`. Enquanto o formato não mudar, a chave permanece `v1`.
 */
export const QUEUE_SCHEMA_VERSION = 1;

/** Teto de posições persistidas (LGPD: retenção mínima; ações nunca são podadas). */
export const MAX_PERSISTED_LOCATIONS = 500;

interface QueueSnapshot {
  schema: number;
  sessionOwner?: QueueOwner | null;
  items: QueueItem[];
}

export interface DiscardRecord {
  clientActionId: string;
  kind: QueueItem["kind"];
  reason: string;
  at: number;
}

/** Contrato mínimo de storage assíncrono (AsyncStorage, MMKV ou fake). */
export interface AsyncKV {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
}

/** KV em memória — fallback quando o storage nativo não está disponível. */
export function createMemoryAsyncKV(): AsyncKV {
  const values = new Map<string, string>();
  return {
    async getItem(key) {
      return values.get(key) ?? null;
    },
    async setItem(key, value) {
      values.set(key, value);
    },
  };
}

/** Forma mínima usada do @react-native-async-storage/async-storage. */
export interface AsyncStorageLike {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
}

/** Adapter do AsyncStorage. Rejeitado pelo contrato → usa memória (fail-safe). */
export function createAsyncStorageKV(backend: AsyncStorageLike): AsyncKV {
  if (
    !backend ||
    typeof backend.getItem !== "function" ||
    typeof backend.setItem !== "function"
  ) {
    throw new TypeError("AsyncStorageInválido");
  }
  return {
    getItem: (key) => backend.getItem(key),
    setItem: (key, value) => backend.setItem(key, value),
  };
}

function cloneItem(item: QueueItem): QueueItem {
  return { ...item, payload: { ...item.payload } };
}

/** Lê lista legada (array puro) ou snapshot versionado ({schema, items}). */
function normalizeSnapshot(parsed: unknown): unknown[] | null {
  if (Array.isArray(parsed)) return parsed;
  if (parsed && typeof parsed === "object" && Array.isArray((parsed as QueueSnapshot).items)) {
    return (parsed as QueueSnapshot).items;
  }
  return null;
}

function snapshotOwner(parsed: unknown): QueueOwner | null {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const owner = (parsed as QueueSnapshot).sessionOwner;
  if (owner && typeof owner.driverId === "string" && owner.driverId) {
    return { driverId: owner.driverId, tenantId: owner.tenantId };
  }
  return null;
}

/** Item persistido só é aceito se tiver o mínimo para ser reenviado. */
function reviveItem(value: unknown): QueueItem | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const id = raw.client_action_id;
  const kind = raw.kind;
  if (typeof id !== "string" || !id) return null;
  if (kind !== "start" && kind !== "arrive" && kind !== "complete" && kind !== "fail" && kind !== "location") {
    return null;
  }
  return {
    client_action_id: id,
    kind,
    deliveryId: typeof raw.deliveryId === "string" ? raw.deliveryId : "",
    payload:
      raw.payload && typeof raw.payload === "object"
        ? ({ ...(raw.payload as Record<string, unknown>) } as Record<string, unknown>)
        : {},
    status: raw.status === "synced" ? "synced" : "pending",
    attempts: Number.isFinite(raw.attempts) ? Math.max(0, Number(raw.attempts)) : 0,
    nextAttemptAt: Number.isFinite(raw.nextAttemptAt) ? Number(raw.nextAttemptAt) : 0,
    createdAt: Number.isFinite(raw.createdAt) ? Number(raw.createdAt) : 0,
    lastError: typeof raw.lastError === "string" ? raw.lastError : undefined,
  };
}

/**
 * Storage sincrono da fila com snapshot persistido.
 *
 * `all()` devolve cópias: o `OfflineQueue` muta o item e chama `save()`, então
 * a fonte de verdade continua sendo este objeto.
 */
export class PersistentQueueStorage implements QueueStorage {
  private items = new Map<string, QueueItem>();
  private kv: AsyncKV;
  private chain: Promise<void> = Promise.resolve();
  private dirty = false;
  private hydrated = false;
  private hydrateFailure: string | null = null;
  private writeFailure: string | null = null;
  /** Identidade da sessão atual (null = sem sessão; nada é reproduzido). */
  private sessionOwner: QueueOwner | null = null;
  /** Auditoria em memória dos descartes explícitos (nenhum descarte implícito). */
  private discards: DiscardRecord[] = [];

  constructor(kv: AsyncKV = createMemoryAsyncKV()) {
    this.kv = kv;
  }

  all(): QueueItem[] {
    return [...this.items.values()].map(cloneItem);
  }

  save(item: QueueItem): void {
    this.items.set(item.client_action_id, cloneItem(item));
    this.enforceLocationCap();
    this.scheduleWrite();
  }

  /** Teto de posições: descarta as mais antigas já sincronizadas/expiradas. */
  private enforceLocationCap(): void {
    const locations = [...this.items.values()]
      .filter((i) => i.kind === "location")
      .sort((a, b) => a.createdAt - b.createdAt);
    let excess = locations.length - MAX_PERSISTED_LOCATIONS;
    if (excess <= 0) return;
    for (const item of locations) {
      if (excess <= 0) break;
      if (item.status !== "synced") continue; // ações/pendentes nunca são podadas
      this.items.delete(item.client_action_id);
      excess -= 1;
    }
  }

  remove(clientActionId: string): void {
    if (!this.items.delete(clientActionId)) return;
    this.scheduleWrite();
  }

  /** Total em memória (inclui synced) — usado em testes/diagnóstico. */
  size(): number {
    return this.items.size;
  }

  get isHydrated(): boolean {
    return this.hydrated;
  }

  /** Último erro de leitura do snapshot (null quando o boot foi limpo). */
  get lastHydrateError(): string | null {
    return this.hydrateFailure;
  }

  /** Último erro de escrita (null quando todas as escritas passaram). */
  get lastWriteError(): string | null {
    return this.writeFailure;
  }

  /** Troca o KV (ex.: memória → AsyncStorage no boot) e reidrata do novo. */
  async attach(kv: AsyncKV): Promise<void> {
    await this.whenIdle();
    this.kv = kv;
    this.hydrated = false;
    await this.hydrate();
  }

  // ── Identidade de sessão (proprietário da fila) ──────────────────────

  /**
   * Define quem é o dono da fila AGORA. `null` = sem sessão (logout).
   *
   * Nada é apagado aqui: ações pendentes são preservadas entre sessões e
   * deixam de ser reproduzidas enquanto não pertencerem à sessão autenticada.
   */
  setSessionOwner(owner: QueueOwner | null): void {
    this.sessionOwner = owner && owner.driverId ? owner : null;
    this.scheduleWrite();
  }

  getSessionOwner(): QueueOwner | null {
    return this.sessionOwner;
  }

  /**
   * Adota itens órfãos (sem `owner`) para a identidade informada.
   *
   * Só cabe aqui quem acabou de resolver a própria identidade no processo, ou
   * cuja identidade coincide com a gravada no snapshot. Itens de outra
   * identidade nunca são adotados — ficam visíveis e pendentes.
   */
  claimUnowned(actor: QueueOwner): number {
    if (!actor || !actor.driverId) return 0;
    // Nunca adotar para outra identidade já conhecida da sessão.
    if (this.sessionOwner && !ownerMatches(this.sessionOwner, actor)) return 0;
    let claimed = 0;
    for (const item of [...this.items.values()]) {
      if (item.owner) continue;
      this.items.set(item.client_action_id, { ...cloneItem(item), owner: actor });
      claimed += 1;
    }
    if (claimed) this.scheduleWrite();
    return claimed;
  }

  /** Itens pendentes que NÃO pertencem à identidade atual (preservados). */
  heldForOtherOwner(actor: QueueOwner | null): QueueItem[] {
    return this.all().filter(
      (i) => i.status === "pending" && !ownerMatches(i.owner, actor ?? undefined),
    );
  }

  // ── Descarte explícito e rastreável ───────────────────────────────

  /**
   * Remove UMA ação de forma explícita e rastreável. Não existe descarte
   * implícito: logout, troca de motorista ou falha de escrita nunca apagam ação.
   */
  discard(clientActionId: string, reason: string): boolean {
    const item = this.items.get(clientActionId);
    if (!item) return false;
    this.discards.push({
      clientActionId,
      kind: item.kind,
      reason,
      at: Date.now(),
    });
    if (this.discards.length > 50) this.discards.shift();
    this.items.delete(clientActionId);
    this.scheduleWrite();
    return true;
  }

  /** Auditoria em memória dos descartes (diagnóstico/telemetria local). */
  getDiscards(): DiscardRecord[] {
    return this.discards.map((d) => ({ ...d }));
  }

  /**
   * Reidrata do KV preservando o que já está em memória.
   *
   * Regras de merge (nenhuma delas pode perder ação ou duplicar envio):
   * - ação confirmada no snapshot vence ação pendente local;
   * - ação já `synced` local nunca volta para `pending`;
   * - em empate, vence a que tem mais tentativas (backoff mais avançado).
   */
  async hydrate(): Promise<void> {
    this.hydrateFailure = null;
    let raw: string | null = null;
    try {
      raw = await this.kv.getItem(QUEUE_STORAGE_KEY);
    } catch (error) {
      this.hydrateFailure = error instanceof Error ? error.message : String(error);
      return;
    }
    if (raw) {
      try {
        const parsed: unknown = JSON.parse(raw);
        const items = normalizeSnapshot(parsed);
        if (items) {
          for (const value of items) {
            const item = reviveItem(value);
            if (item) this.merge(item);
          }
          // Identidade gravada só é adotada quando a atual ainda é desconhecida.
          if (!this.sessionOwner && snapshotOwner(parsed)) {
            this.sessionOwner = snapshotOwner(parsed);
          }
        } else {
          this.hydrateFailure = "snapshot não é lista nem objeto válido";
        }
      } catch (error) {
        this.hydrateFailure = error instanceof Error ? error.message : String(error);
      }
    }
    this.hydrated = true;
  }

  private merge(incoming: QueueItem): void {
    const current = this.items.get(incoming.client_action_id);
    if (!current) {
      this.items.set(incoming.client_action_id, cloneItem(incoming));
      return;
    }
    if (current.status === "synced") return;
    if (incoming.status === "synced" || incoming.attempts > current.attempts) {
      this.items.set(incoming.client_action_id, cloneItem(incoming));
    }
  }

  /** Remove tudo (logout explícito) e persiste o snapshot vazio. */
  clear(): void {
    if (this.items.size === 0) return;
    this.items.clear();
    this.scheduleWrite();
  }

  /** Aguarda todas as escritas pendentes (boot/teste/desligamento). */
  async whenIdle(): Promise<void> {
    await this.chain;
  }

  /**
   * Obrigatório pelo contrato `QueueStorage.persist`: só resolve quando a
   * gravação durável concluiu; **propaga** se a última escrita falhou, para o
   * chamador não confirmar “salvo” com o disco desatualizado.
   */
  async persist(): Promise<void> {
    // Se a escrita anterior falhou, o snapshot segue “sujo”: aqui é onde a
    // nova tentativa acontece (o chamador só pode confirmar quando gravar).
    if (this.dirty) this.scheduleWrite();
    await this.chain;
    if (this.writeFailure) {
      throw new Error(`fila offline não pôde ser gravada: ${this.writeFailure}`);
    }
  }

  private scheduleWrite(): void {
    this.dirty = true;
    this.chain = this.chain.then(() => this.writeIfDirty());
  }

  private async writeIfDirty(): Promise<void> {
    if (!this.dirty) return;
    this.dirty = false;
    const payload = JSON.stringify({
      schema: QUEUE_SCHEMA_VERSION,
      sessionOwner: this.sessionOwner,
      items: [...this.items.values()],
    } satisfies QueueSnapshot);
    try {
      await this.kv.setItem(QUEUE_STORAGE_KEY, payload);
      this.writeFailure = null;
    } catch (error) {
      // Mantém sujo para a próxima mutação tentar de novo; a fila continua
      // válida em memória (offline degradado não pode travar a operação).
      this.dirty = true;
      this.writeFailure = error instanceof Error ? error.message : String(error);
    }
  }
}
