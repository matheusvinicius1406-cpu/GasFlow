/**
 * offlineQueue — fila offline persistente do App do Entregador (prompt 5.4).
 *
 * Módulo puro: o storage (SQLite) e o transporte (fetch) são injetados —
 * testável via node --test e reutilizável no RN real.
 *
 * Contrato do prompt:
 * - cada ação ganha client_action_id (UUID) ANTES de sair da tela
 * - ações ficam status "pending" até o servidor confirmar
 * - retry com backoff exponencial; sucesso marca "synced"
 * - a fila sobrevive ao fechamento do app (storage persistente injetado)
 */

export type QueueStatus = "pending" | "synced";

/**
 * Proprietário da ação: quem tem direito a reproduzi-la.
 *
 * NUNCA contém token, senha ou credencial — só identificadores opacos de
 * sessão (motorista + tenant). É o que permite preservar a fila no logout
 * sem que a fila de um motorista seja reproduzida sob a sessão de outro.
 */
export interface QueueOwner {
  driverId: string;
  tenantId?: string;
}

/** Identidades são iguais quando motorista e tenant coincidem (tenant ausente casa com qualquer). */
export function ownerMatches(item: QueueOwner | undefined, actor: QueueOwner | undefined): boolean {
  if (!item || !actor) return false;
  if (item.driverId !== actor.driverId) return false;
  if (item.tenantId && actor.tenantId && item.tenantId !== actor.tenantId) return false;
  return true;
}

export interface QueueItem {
  client_action_id: string;
  kind: "start" | "arrive" | "complete" | "fail" | "location";
  deliveryId: string;
  payload: Record<string, unknown>;
  status: QueueStatus;
  attempts: number;
  nextAttemptAt: number; // epoch ms
  createdAt: number;
  lastError?: string;
  /** Proprietário no momento do enqueue (ausente em item herdado/ilegível). */
  owner?: QueueOwner;
  /** Motivo do descarte explícito (rastreabilidade) — só em item removido. */
  discardedReason?: string;
}

export interface QueueStorage {
  all(): QueueItem[];
  save(item: QueueItem): void;
  /** Opcional: quando existe, itens prontos/vencidos são apagados de verdade. */
  remove?(clientActionId: string): void;
  /**
   * Opcional: aguarda a gravação **durável** do snapshot. Quando existe, o
   * `flush` só retorna depois de concluir — assim o chamador nunca confirma
   * “ação salva” antes de a escrita terminar (prompt 3.1).
   */
  persist?(): Promise<void>;
}

/** Fase 5: retenção local das posições (mesma janela da lib de background). */
export const LOCATION_RETENTION_DAYS = 7;

const BASE_BACKOFF_MS = 2_000;
const MAX_BACKOFF_MS = 5 * 60_000;

/** UUID quando disponível (node/browser), fallback determinístico no Hermes. */
function defaultId(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    /* cai no fallback */
  }
  return `act-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

export class OfflineQueue {
  /** Público readonly para inspeção em testes (não mutar diretamente). */
  readonly storage: QueueStorage;
  private clock: () => number;
  private idGen: () => string;

  constructor(storage: QueueStorage, clock: () => number = () => Date.now(), idGen: () => string = defaultId) {
    this.storage = storage;
    this.clock = clock;
    this.idGen = idGen;
  }

  /** Registra ação ANTES do envio — id gerado aqui (prompt: "cada ação inclui client_action_id"). */
  enqueue(
    kind: QueueItem["kind"],
    deliveryId: string,
    payload: Record<string, unknown> = {},
    owner?: QueueOwner,
  ): QueueItem {
    // Fase 5: posições são append-only — deduplica por `recorded_at` (replay do
    // background não empilha o mesmo ponto) e aplica a retenção local de 7 dias.
    if (kind === "location") {
      const duplicate = this.findLocationByRecordedAt(payload.recorded_at);
      if (duplicate) return duplicate;
      this.pruneLocations();
    }

    const item: QueueItem = {
      client_action_id: this.idGen(),
      kind,
      deliveryId,
      payload,
      status: "pending",
      attempts: 0,
      nextAttemptAt: this.clock(),
      createdAt: this.clock(),
      owner,
    };
    this.storage.save(item);
    return item;
  }

  /** Posição já enfileirada com o mesmo `recorded_at` (idempotência do replay). */
  private findLocationByRecordedAt(recordedAt: unknown): QueueItem | null {
    if (typeof recordedAt !== "string" || !recordedAt) return null;
    return (
      this.storage
        .all()
        .find((i) => i.kind === "location" && i.payload.recorded_at === recordedAt) ?? null
    );
  }

  /**
   * Descarta posições já enviadas ou vencidas (default 7 dias).
   *
   * Com `storage.remove` apaga de fato; sem ele, apenas marca como `synced`
   * para que `pending()` não as reenvie.
   */
  pruneLocations(retentionDays: number = LOCATION_RETENTION_DAYS): number {
    const cutoff = this.clock() - retentionDays * 24 * 60 * 60 * 1000;
    let removed = 0;
    for (const item of this.storage.all()) {
      if (item.kind !== "location") continue;
      const isSynced = item.status === "synced";
      const isExpired = item.createdAt < cutoff;
      if (!isSynced && !isExpired) continue;
      if (this.storage.remove) {
        this.storage.remove(item.client_action_id);
      } else {
        item.status = "synced";
      }
      removed += 1;
    }
    return removed;
  }

  pending(): QueueItem[] {
    const now = this.clock();
    return this.storage
      .all()
      .filter((i) => i.status === "pending" && i.nextAttemptAt <= now)
      .sort((a, b) => a.createdAt - b.createdAt);
  }

  /**
   * Um tick do worker: tenta enviar cada ação pendente via o transport injetado.
   *
   * `opts.owner` é a identidade autenticada **agora**. Quando informada, só
   * itens cujo `owner` casa são reproduzidos: os de outro motorista/tenant
   * são deixados de lado — preservados, nunca descartados e nunca reenviados
   * sob esta sessão (o contador desses itens fica em
   * `heldForOtherOwner()` no storage). Sem `opts` o comportamento é o
   * histórico (todos os pendentes), preservando compatibilidade com os testes
   * existentes.
   *
   * Ao final, quando o storage oferece `persist()`, aguarda a gravação durável:
   * o retorno {sent, failed} só sai depois de o snapshot ter sido escrito.
   */
  async flush(
    transport: (item: QueueItem) => Promise<void>,
    opts: { owner?: QueueOwner } = {},
  ): Promise<{ sent: number; failed: number }> {
    let sent = 0;
    let failed = 0;
    const actor = opts.owner;
    for (const item of this.pending()) {
      if (actor && !ownerMatches(item.owner, actor)) {
        // Sem correspondência de proprietário: mantém pendente (visível), não
        // envia e não apaga. Reprovação explícita de replay indevido.
        continue;
      }
      try {
        await transport(item);
        item.status = "synced";
        item.lastError = undefined;
        sent += 1;
      } catch (e) {
        item.attempts += 1;
        item.lastError = e instanceof Error ? e.message : String(e);
        item.nextAttemptAt = this.clock() + this.backoffMs(item);
        failed += 1;
      }
      this.storage.save(item);
    }
    if (this.storage.persist) {
      // Falha aqui é propagada: o chamador não pode afirmar que a ação está
      // salva/descarregada quando a gravação durável não concluiu.
      await this.storage.persist();
    }
    return { sent, failed };
  }

  /** Backoff para a próxima tentativa: 2s, 4s, 8s… cap 5min. */
  backoffMs(item: QueueItem): number {
    return Math.min(BASE_BACKOFF_MS * Math.pow(2, Math.max(0, item.attempts - 1)), MAX_BACKOFF_MS);
  }

  count(): { pending: number; synced: number } {
    const all = this.storage.all();
    return {
      pending: all.filter((i) => i.status === "pending").length,
      synced: all.filter((i) => i.status === "synced").length,
    };
  }
}
