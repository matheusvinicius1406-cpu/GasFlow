/**
 * GasFlow Integration Agent — ponto de entrada.
 *
 * Pull model: a cada AGENT_POLL_INTERVAL_SEC o agente pergunta ao backend
 * quais integrações estão due e executa. Alternativa cron: `npm run once`.
 *
 * Env:
 *   GASFLOW_API_URL          — URL do backend (default http://localhost:8000)
 *   GASFLOW_SERVICE_TOKEN    — token/senha de usuário de serviço com integration.write
 *   AGENT_POLL_INTERVAL_SEC  — intervalo do poll (default 60)
 *   AGENT_RUN_ONCE           — "1" executa uma rodada e sai (equivale a --once)
 *
 * Modo desktop: `--ipc` entra no protocolo JSON-lines sobre stdin/stdout
 * (comandos ping/configure/listIntegrations/sync/shutdown — ver ipc.ts),
 * usado pelo app desktop Electron para controlar o agente como subprocesso.
 *
 * O agente opera APENAS sobre sites do próprio dono da integração (ou com
 * autorização): HTTP direto com as credenciais configuradas, sem evasão.
 */

import { runIpcMode } from "./ipc";
import { GasFlowClient } from "./gasflow-client";
import { runDueIntegrations } from "./runner";

interface CliArgs {
  once: boolean;
  intervalSec: number;
  apiUrl: string;
  token: string;
}

function parseArgs(): CliArgs {
  const onceFlag = process.argv.includes("--once");
  const env = {
    once: onceFlag || process.env.AGENT_RUN_ONCE === "1",
    intervalSec: Number.parseInt(process.env.AGENT_POLL_INTERVAL_SEC ?? "60", 10),
    apiUrl: process.env.GASFLOW_API_URL ?? "http://localhost:8000",
    token: process.env.GASFLOW_SERVICE_TOKEN ?? "",
  };
  return {
    once: env.once,
    intervalSec: Number.isFinite(env.intervalSec) && env.intervalSec > 5 ? env.intervalSec : 60,
    apiUrl: env.apiUrl,
    token: env.token,
  };
}

function log(msg: string): void {
  console.log(`[agent ${new Date().toISOString()}] ${msg}`);
}

async function runOnce(client: GasFlowClient): Promise<boolean> {
  log("iniciando rodada de sincronização…");
  try {
    const outcomes = await runDueIntegrations(client);
    if (outcomes.length === 0) {
      log("nenhuma integração due.");
      return true;
    }
    let allOk = true;
    for (const o of outcomes) {
      log(`${o.ok ? "OK" : "ERRO"} [${o.integrationName}] ${o.message}`);
      for (const err of o.errors.slice(0, 10)) {
        log(`  ⚠ ${err.external_ref ?? "?"}: ${err.message}`);
      }
      if (!o.ok) allOk = false;
    }
    return allOk;
  } catch (e) {
    log(`falha na rodada: ${(e as Error).message}`);
    return false;
  }
}

async function main(): Promise<void> {
  // Modo desktop (Electron): protocolo IPC, sem exigir token no boot —
  // as credenciais chegam depois via comando `configure`.
  if (process.argv.includes("--ipc")) {
    runIpcMode();
    return;
  }

  const args = parseArgs();
  if (!args.token) {
    console.error("GASFLOW_SERVICE_TOKEN não configurado — abortando.");
    process.exit(2);
  }
  const client = new GasFlowClient({ baseUrl: args.apiUrl, token: args.token });
  log(`agente iniciado — API ${args.apiUrl}, poll ${args.intervalSec}s`);

  if (args.once) {
    const ok = await runOnce(client);
    process.exit(ok ? 0 : 1);
  }

  let consecutiveFailures = 0;
  for (;;) {
    const ok = await runOnce(client);
    consecutiveFailures = ok ? 0 : consecutiveFailures + 1;
    if (consecutiveFailures >= 5) {
      log("5 falhas consecutivas — saindo para o supervisor reiniciar.");
      process.exit(1);
    }
    await new Promise((resolve) => setTimeout(resolve, args.intervalSec * 1000));
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
