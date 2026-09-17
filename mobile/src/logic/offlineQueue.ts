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

export interface QueueItem {
  client_action_id: string;
  kind: "start" | "complete" | "fail" | "location";
  deliveryId: string;
  payload: Record<string, unknown>;
  status: QueueStatus;
  attempts: number;
  nextAttemptAt: number; // epoch ms
  createdAt: number;
  lastError?: string;
}

export interface QueueStorage {
  all(): QueueItem[];
  save(item: QueueItem): void;
}

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
  enqueue(kind: QueueItem["kind"], deliveryId: string, payload: Record<string, unknown> = {}): QueueItem {
    const item: QueueItem = {
      client_action_id: this.idGen(),
      kind,
      deliveryId,
      payload,
      status: "pending",
      attempts: 0,
      nextAttemptAt: this.clock(),
      createdAt: this.clock(),
    };
    this.storage.save(item);
    return item;
  }

  pending(): QueueItem[] {
    const now = this.clock();
    return this.storage
      .all()
      .filter((i) => i.status === "pending" && i.nextAttemptAt <= now)
      .sort((a, b) => a.createdAt - b.createdAt);
  }

  /** Um tick do worker: tenta enviar cada ação pendente via o transport injetado. */
  async flush(transport: (item: QueueItem) => Promise<void>): Promise<{ sent: number; failed: number }> {
    let sent = 0;
    let failed = 0;
    for (const item of this.pending()) {
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
