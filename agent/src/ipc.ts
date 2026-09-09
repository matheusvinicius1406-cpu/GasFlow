/**
 * Modo IPC do agente (--ipc): protocolo de linhas JSON sobre stdin/stdout.
 *
 * Usado pelo app desktop (Electron), que controla o agente como subprocesso:
 *   → pedidos:   {"id":"1","cmd":"ping","params":{}}
 *   ← resposta:  {"id":"1","ok":true,"data":{...}}
 *   ← eventos (sem id): {"event":"log","level":"info","message":"..."}
 *
 * Comandos: ping | configure | listIntegrations | sync | shutdown
 *
 * `sync` responde quando TODAS as integrações terminam (pode demorar — o
 * chamador deve usar timeout generoso); enquanto isso emite eventos
 * `outcome` em tempo real para a UI.
 *
 * Fora do modo IPC o comportamento do agente não muda (poll loop / --once).
 */

import { createInterface } from "node:readline";
import { GasFlowClient } from "./gasflow-client";
import { runDueIntegrations, syncIntegration, type SyncOutcome } from "./runner";
import type { IntegrationConfig } from "./types";

type Params = Record<string, unknown>;

interface IpcRequest {
  id?: string;
  cmd?: string;
  params?: Params;
}

/** Linhas emitidas pelo agente no modo IPC (sempre JSON válido, uma por linha). */
export type IpcOutLine =
  | { id: string; ok: true; data: unknown }
  | { id: string; ok: false; error: string }
  | { event: "ready" }
  | { event: "log"; level: "info" | "error"; message: string }
  | { event: "outcome"; outcome: SyncOutcome };

interface IpcState {
  client: GasFlowClient | null;
  apiUrl: string;
  busy: boolean;
}

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function bool(v: unknown): boolean {
  return v === true || v === "true";
}

function outcomeOf(integration: IntegrationConfig, e: unknown): SyncOutcome {
  return {
    integrationId: integration.id,
    integrationName: integration.name,
    ok: false,
    totalFound: 0,
    imported: 0,
    errors: [],
    message: `Falha na sincronização: ${(e as Error).message}`,
  };
}

/** Executa um comando e devolve as linhas de saída (testável, sem I/O global). */
async function handleLine(
  raw: string,
  state: IpcState,
  emit: (line: IpcOutLine) => void
): Promise<void> {
  const line = raw.trim();
  if (!line) return;

  let req: IpcRequest;
  try {
    req = JSON.parse(line) as IpcRequest;
  } catch {
    emit({ id: "", ok: false, error: "linha inválida — JSON não pôde ser parseado" });
    return;
  }
  const id = str(req.id);
  const params: Params = req.params ?? {};
  const requireClient = (): GasFlowClient => {
    if (!state.client) throw new Error("agente não configurado — envie {cmd:'configure', params:{apiUrl, token}} primeiro");
    return state.client;
  };

  try {
    switch (req.cmd) {
      case "ping": {
        emit({ id, ok: true, data: { pong: true, pid: process.pid, mode: "ipc" } });
        break;
      }

      case "configure": {
        const apiUrl = str(params.apiUrl).replace(/\/+$/, "") || "http://localhost:8000";
        const token = str(params.token);
        if (!token) throw new Error("configure: token é obrigatório");
        state.client = new GasFlowClient({ baseUrl: apiUrl, token });
        state.apiUrl = apiUrl;
        emit({ id, ok: true, data: { configured: true, apiUrl } });
        emit({ event: "log", level: "info", message: `agente configurado — API ${apiUrl}` });
        break;
      }

      case "listIntegrations": {
        const client = requireClient();
        const integrations = await client.listIntegrations(bool(params.includeInactive));
        emit({ id, ok: true, data: { integrations, count: integrations.length } });
        break;
      }

      case "sync": {
        if (state.busy) throw new Error("sync já em execução — aguarde o término");
        const client = requireClient();
        state.busy = true;
        void (async () => {
          try {
            const targetId = str(params.integrationId);
            let targets: IntegrationConfig[];
            if (targetId) {
              const all = await client.listIntegrations(true);
              const found = all.find((i) => i.id === targetId);
              if (!found) throw new Error(`integração "${targetId}" não encontrada`);
              targets = [found];
            } else {
              targets = await client.dueIntegrations();
              emit({ event: "log", level: "info", message: `sincronizando ${targets.length} integração(ões) due…` });
            }

            let okCount = 0;
            let failCount = 0;
            for (const integration of targets) {
              try {
                const outcome = await syncIntegration(integration, client);
                outcome.ok ? okCount++ : failCount++;
                emit({ event: "outcome", outcome });
              } catch (e) {
                failCount++;
                emit({ event: "outcome", outcome: outcomeOf(integration, e) });
              }
            }
            emit({ id, ok: true, data: { total: targets.length, okCount, failCount } });
          } catch (e) {
            emit({ id, ok: false, error: `Falha na sincronização: ${(e as Error).message}` });
          } finally {
            state.busy = false;
          }
        })();
        break;
      }

      case "shutdown": {
        emit({ id, ok: true, data: { bye: true } });
        emit({ event: "log", level: "info", message: "shutdown solicitado pelo desktop" });
        setTimeout(() => process.exit(0), 50);
        break;
      }

      default:
        emit({ id, ok: false, error: `comando desconhecido: ${String(req.cmd)}` });
    }
  } catch (e) {
    emit({ id, ok: false, error: (e as Error).message });
  }
}

/**
 * Cria o loop IPC sobre um stream de entrada (testável — usa PassThrough nos
 * testes, process.stdin no app desktop). Cada linha emitida sai via `emit`.
 * O encerramento por fim-de-stdin fica a cargo de quem faz a fiação.
 */
export function createAgentIpc(
  input: NodeJS.ReadableStream,
  emit: (line: IpcOutLine) => void
): void {
  const state: IpcState = { client: null, apiUrl: "", busy: false };
  emit({ event: "ready" });
  const rl = createInterface({ input, terminal: false });
  rl.on("line", (raw) => {
    void handleLine(raw, state, emit);
  });
}

/** Fiação do modo IPC real: stdin → handler, handler → stdout (JSON lines). */
export function runIpcMode(): void {
  const emit = (line: IpcOutLine): void => {
    process.stdout.write(`${JSON.stringify(line)}\n`);
  };
  createAgentIpc(process.stdin, emit);
  emit({ event: "log", level: "info", message: `agente em modo IPC — pid ${process.pid}` });
  // stdin fechado (pai morreu) → encerra para não virar órfão.
  process.stdin.on("end", () => process.exit(0));
  process.stdin.on("error", () => process.exit(1));
  // Mantém o processo vivo enquanto o stdin estiver aberto.
  process.stdin.resume();
}
