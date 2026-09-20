/**
 * PrintWorker — F10.7
 *
 * Liga a fila de impressão do backend à impressora USB desta máquina:
 *
 *   a cada poll → GET /printer/agent/next (X-GasFlow-Key)
 *     com job → imprime os bytes ESC/POS → POST .../result (sucesso ou motivo)
 *     sem job → reporta estado da impressora (ONLINE) e espera o próximo poll
 *
 * Sem impressora configurada, reporta NOT_CONFIGURED (a tela de impressão
 * mostra isso em vez de o operador achar que imprimiu) e não consome a fila.
 *
 * Nunca lança: falha de rede/impressora vira estado + evento, para o worker
 * ser apenas mais um serviço sob o orquestrador (F10.3).
 *
 * Anti-duplicata: o `PrintedJobLedger` lembra o que já foi para o spooler. Se o
 * backend devolver o job à fila (o POST do resultado se perdeu), o cupom NÃO
 * sai de novo — o worker só re-reporta o sucesso.
 */

import { printRawBytes, type RawPrintResult } from "./print-transport";
import { PrintedJobLedger } from "./printed-jobs";

export type PrinterState = "ONLINE" | "OFFLINE" | "ERROR" | "NOT_CONFIGURED";

export interface PrintWorkerOptions {
    /** Ex.: http://127.0.0.1:8000 */
    baseUrl: string;
    /** Chave de serviço do backend (X-GasFlow-Key). */
    serviceKey: string;
    /** Nome da impressora no Windows (vazio = não configurada). */
    printerName: string;
    /** Intervalo do poll em ms (default 3s). */
    pollMs?: number;
    fetchFn?: typeof fetch;
    /** Injetável nos testes: impressão de verdade por padrão. */
    printFn?: (printerName: string, data: Buffer) => Promise<RawPrintResult>;
    /**
     * Onde lembrar os jobs já enviados ao spooler (userData/printed-jobs.json).
     * Sem caminho, o ledger vive só na memória desta execução.
     */
    ledgerPath?: string;
    onEvent?: (event: PrintWorkerEvent) => void;
}

export interface PrintWorkerEvent {
    /** `replayed` = já tinha saído nesta máquina; não foi reimpresso. */
    type: "printed" | "replayed" | "failed" | "expired" | "idle_error";
    orderId?: string;
    detail: string;
}

export interface PrintWorkerStatus {
    running: boolean;
    printerName: string;
    state: PrinterState;
    printed: number;
    /** Cupons repetidos que NÃO saíram de novo (job devolvido à fila). */
    replayed: number;
    failed: number;
    lastTickAt: number | null;
    lastError: string;
}

/** O que o backend respondeu quando o agente perguntou "tem job pra mim?". */
type FetchNextResult =
    | { kind: "job"; job: { id: string; order_id: string }; escpos_base64: string; expiredJobs: number }
    | { kind: "empty"; expiredJobs: number }
    | { kind: "error"; detail: string };

const DEFAULT_POLL_MS = 3_000;
/** Um worker sem tick recente é considerado doente pelo orquestrador. */
const STALE_MULTIPLIER = 4;

export class PrintWorker {
    private opts: PrintWorkerOptions;
    private timer: ReturnType<typeof setInterval> | null = null;
    private ticking = false;
    private printed = 0;
    private replayed = 0;
    private failed = 0;
    private lastTickAt: number | null = null;
    private lastError = "";
    private state: PrinterState = "NOT_CONFIGURED";
    /**
     * Último total de vencidos que JÁ avisamos. O vencimento nasce no backend
     * (cupom de dia anterior) e o agente é quem tem a chance de contar — se
     * ninguém avisar, o pedido fica sem cupom em silêncio.
     */
    private lastNotifiedExpired = 0;
    /**
     * Último estado CONFIRMADO pelo backend — evita POST a cada poll ocioso.
     * Só é gravado depois de o POST ter ido bem: cachear antes fazia um relato
     * perdido nunca mais ser reenviado (o backend reinicia, esquece o estado, e
     * a tela fica presa em "Não configurada" com a impressora funcionando).
     */
    private reportedState: PrinterState | null = null;
    private reportedDetail = "";
    private ledger: PrintedJobLedger;

    constructor(opts: PrintWorkerOptions) {
        this.opts = opts;
        this.ledger = new PrintedJobLedger(opts.ledgerPath);
    }

    get running(): boolean {
        return this.timer !== null;
    }

    start(): void {
        if (this.timer) return;
        const interval = this.opts.pollMs ?? DEFAULT_POLL_MS;
        void this.tick();
        this.timer = setInterval(() => void this.tick(), interval);
        this.timer.unref?.();
    }

    stop(): void {
        if (this.timer) clearInterval(this.timer);
        this.timer = null;
    }

    status(): PrintWorkerStatus {
        return {
            running: this.running,
            printerName: this.opts.printerName,
            state: this.state,
            printed: this.printed,
            replayed: this.replayed,
            failed: this.failed,
            lastTickAt: this.lastTickAt,
            lastError: this.lastError,
        };
    }

    /** Saúde para o orquestrador: rodando e com tick recente. */
    isHealthy(): boolean {
        if (!this.running) return false;
        if (this.lastTickAt === null) return true; // ainda não tickou: subindo
        const interval = this.opts.pollMs ?? DEFAULT_POLL_MS;
        return Date.now() - this.lastTickAt < interval * STALE_MULTIPLIER;
    }

    /** Troca a impressora sem reiniciar o app. */
    setPrinterName(printerName: string): void {
        this.opts = { ...this.opts, printerName };
        this.state = printerName ? "ONLINE" : "NOT_CONFIGURED";
        // Força o próximo ciclo a publicar o novo estado
        this.reportedState = null;
        this.reportedDetail = "";
    }

    /** Um ciclo: pega no máximo um job e reporta o estado. Público para testes. */
    async tick(): Promise<{ printed: boolean; orderId?: string }> {
        if (this.ticking) return { printed: false };
        this.ticking = true;
        try {
            if (!this.opts.printerName) {
                this.state = "NOT_CONFIGURED";
                this.lastTickAt = Date.now();
                await this.reportStatus("NOT_CONFIGURED", "impressora não escolhida nas configurações");
                return { printed: false };
            }

            const claimed = await this.fetchNext();
            if (claimed.kind === "error") {
                // Erro de rede/back-end/chave: não marca como impressora offline
                // (o problema pode ser o backend, não a térmica).
                this.state = "ERROR";
                this.lastError = claimed.detail;
                this.lastTickAt = Date.now();
                return { printed: false };
            }

            if (claimed.kind === "empty") {
                this.state = "ONLINE";
                this.lastError = "";
                this.lastTickAt = Date.now();
                this.notifyExpired(claimed.expiredJobs);
                await this.reportStatus("ONLINE", "");
                return { printed: false };
            }

            this.notifyExpired(claimed.expiredJobs);

            const job = claimed.job;

            if (this.ledger.has(job.id)) {
                // Já saiu nesta máquina: o backend devolveu o job à fila porque
                // o POST do resultado se perdeu. Reimprimir aqui daria dois
                // cupons do mesmo pedido — re-reporta o sucesso e segue.
                this.replayed += 1;
                this.state = "ONLINE";
                this.lastError = "";
                this.lastTickAt = Date.now();
                await this.reportResult(job.id, { ok: true });
                await this.reportStatus("ONLINE", "");
                this.emit({
                    type: "replayed",
                    orderId: job.order_id,
                    detail: `pedido #${job.order_id} já havia saído nesta máquina — não reimprimiu`,
                });
                return { printed: false, orderId: job.order_id };
            }

            const result = await (this.opts.printFn ?? printRawBytes)(
                this.opts.printerName,
                Buffer.from(claimed.escpos_base64, "base64")
            );

            if (result.ok) {
                // Só depois do spooler aceitar: é isto que impede a duplicata
                // quando o relato do resultado se perde a caminho do backend.
                this.ledger.remember(job.id);
            }

            await this.reportResult(job.id, result);

            if (result.ok) {
                this.printed += 1;
                this.state = "ONLINE";
                this.lastError = "";
                this.emit({
                    type: "printed",
                    orderId: job.order_id,
                    detail: `pedido #${job.order_id} impresso`,
                });
            } else {
                this.failed += 1;
                this.state = "ERROR";
                this.lastError = result.error ?? "falha ao imprimir";
                this.emit({
                    type: "failed",
                    orderId: job.order_id,
                    detail: `pedido #${job.order_id}: ${this.lastError}`,
                });
            }
            this.lastTickAt = Date.now();
            await this.reportStatus(this.state, result.ok ? "" : this.lastError);
            return { printed: result.ok, orderId: job.order_id };
        } catch (e) {
            // Best-effort: nada aqui pode derrubar o processo do app.
            this.lastError = e instanceof Error ? e.message : String(e);
            this.lastTickAt = Date.now();
            this.emit({ type: "idle_error", detail: this.lastError });
            return { printed: false };
        } finally {
            this.ticking = false;
        }
    }

    // ── HTTP ───────────────────────────────────────────────────

    private headers(): Record<string, string> {
        return { "Content-Type": "application/json", "X-GasFlow-Key": this.opts.serviceKey };
    }

    private async fetchNext(): Promise<FetchNextResult> {
        const fetchFn = this.opts.fetchFn ?? fetch;
        const offline = "não foi possível consultar a fila de impressão";
        try {
            const res = await fetchFn(`${this.opts.baseUrl}/printer/agent/next`, {
                headers: this.headers(),
                signal: AbortSignal.timeout(10_000),
            });
            // 401/403 merecem diagnóstico próprio: sem isso, uma chave de serviço
            // errada/rotacionada aparece para sempre como "backend fora".
            if (res.status === 401 || res.status === 403) {
                return {
                    kind: "error",
                    detail: `chave de serviço rejeitada pelo backend (HTTP ${res.status}) — confira a chave configurada no app`,
                };
            }
            if (!res.ok) {
                return { kind: "error", detail: `${offline} (backend respondeu HTTP ${res.status})` };
            }
            const body = (await res.json()) as {
                job: { id: string; order_id: string } | null;
                escpos_base64: string | null;
                expired_jobs?: number;
            };
            const expiredJobs = Number(body?.expired_jobs ?? 0) || 0;
            if (!body?.job) return { kind: "empty", expiredJobs };
            return {
                kind: "job",
                job: body.job,
                escpos_base64: body.escpos_base64 ?? "",
                expiredJobs,
            };
        } catch {
            return { kind: "error", detail: offline };
        }
    }

    private async reportResult(jobId: string, result: RawPrintResult): Promise<void> {
        const fetchFn = this.opts.fetchFn ?? fetch;
        try {
            await fetchFn(`${this.opts.baseUrl}/printer/agent/jobs/${jobId}/result`, {
                method: "POST",
                headers: this.headers(),
                body: JSON.stringify({
                    success: result.ok,
                    error: result.error ?? "",
                    printer_name: this.opts.printerName,
                }),
                signal: AbortSignal.timeout(10_000),
            });
        } catch {
            /* se o backend caiu, o job volta para a fila pelo timeout de claim */
        }
    }

    /**
     * Publica o estado no backend só quando muda (ou quando um resultado de
     * impressão precisa ser registrado) — evita um POST a cada 3s parado.
     */
    private async reportStatus(status: PrinterState, detail: string): Promise<void> {
        if (status === this.reportedState && detail === this.reportedDetail) return;
        const fetchFn = this.opts.fetchFn ?? fetch;
        try {
            const res = await fetchFn(`${this.opts.baseUrl}/printer/agent/status`, {
                method: "POST",
                headers: this.headers(),
                body: JSON.stringify({ status, printer_name: this.opts.printerName, detail }),
                signal: AbortSignal.timeout(10_000),
            });
            if (!res?.ok) return; // backend não registrou: o próximo tick tenta de novo
            // Cache só do que o backend CONFIRMOU (ver comentário do campo).
            this.reportedState = status;
            this.reportedDetail = detail;
        } catch {
            /* status é informativo — não vale falhar o ciclo por isso */
        }
    }

    /**
     * Avisa (uma vez) que existem cupons vencidos na fila.
     *
     * Só quando o total AUMENTA: o poll é a cada 3s e avisar sempre seria spam; e
     * o total só cresce (job vencido não sai da fila, o operador reimprime).
     * Na primeira volta depois de abrir o app o total aparece de uma vez — é
     * exatamente quando o operador precisa saber.
     */
    private notifyExpired(count: number): void {
        if (count <= this.lastNotifiedExpired) return;
        this.lastNotifiedExpired = count;
        this.emit({
            type: "expired",
            detail: `${count} cupom(ns) de dia anterior não saíram — reimprima os que ainda precisar`,
        });
    }

    private emit(event: PrintWorkerEvent): void {
        this.opts.onEvent?.(event);
    }
}
