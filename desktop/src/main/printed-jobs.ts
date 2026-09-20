/**
 * PrintedJobLedger — F10.7
 *
 * Memória local dos cupons que ESTA máquina já mandou para o spooler.
 *
 * Por que existe: se o POST do resultado se perde (backend reiniciando, túnel
 * caindo), o backend devolve o job à fila depois do timeout de claim — e o
 * agente o pegaria de novo, imprimindo o MESMO cupom duas vezes. O job id é
 * único para sempre, então "já saiu nesta máquina" basta para não repetir.
 * Reimprimir de verdade continua à mão: os botões da tela criam um job NOVO.
 *
 * Guardado em `userData/printed-jobs.json`, limitado aos últimos ids. Qualquer
 * falha de disco é ignorada — perder o arquivo não pode impedir impressão.
 */

import fs from "node:fs";
import path from "node:path";

/** Quantos ids lembrar (um dia de cupons cabe folgado). */
const DEFAULT_LIMIT = 200;

export class PrintedJobLedger {
    private ids: string[] = [];
    private loaded = false;

    constructor(
        private filePath?: string,
        private limit = DEFAULT_LIMIT
    ) {}

    /** Este job já foi para o spooler nesta máquina? */
    has(jobId: string): boolean {
        this.load();
        return this.ids.includes(jobId);
    }

    /** Marca o job como enviado ao spooler. */
    remember(jobId: string): void {
        this.load();
        if (this.ids.includes(jobId)) return;
        this.ids.push(jobId);
        if (this.ids.length > this.limit) this.ids = this.ids.slice(-this.limit);
        this.persist();
    }

    private load(): void {
        if (this.loaded) return;
        this.loaded = true;
        if (!this.filePath) return;
        try {
            const raw: unknown = JSON.parse(fs.readFileSync(this.filePath, "utf-8"));
            this.ids = Array.isArray(raw) ? raw.filter((item): item is string => typeof item === "string") : [];
        } catch {
            // Arquivo ausente/corrompido = ledger vazio (nunca derruba o worker).
            this.ids = [];
        }
    }

    private persist(): void {
        if (!this.filePath) return;
        try {
            fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
            fs.writeFileSync(this.filePath, JSON.stringify(this.ids), "utf-8");
        } catch {
            /* disco é otimização: sem o arquivo o worker apenas perde a memória */
        }
    }
}
