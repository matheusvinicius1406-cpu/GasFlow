"use strict";
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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.PrintedJobLedger = void 0;
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
/** Quantos ids lembrar (um dia de cupons cabe folgado). */
const DEFAULT_LIMIT = 200;
class PrintedJobLedger {
    filePath;
    limit;
    ids = [];
    loaded = false;
    constructor(filePath, limit = DEFAULT_LIMIT) {
        this.filePath = filePath;
        this.limit = limit;
    }
    /** Este job já foi para o spooler nesta máquina? */
    has(jobId) {
        this.load();
        return this.ids.includes(jobId);
    }
    /** Marca o job como enviado ao spooler. */
    remember(jobId) {
        this.load();
        if (this.ids.includes(jobId))
            return;
        this.ids.push(jobId);
        if (this.ids.length > this.limit)
            this.ids = this.ids.slice(-this.limit);
        this.persist();
    }
    load() {
        if (this.loaded)
            return;
        this.loaded = true;
        if (!this.filePath)
            return;
        try {
            const raw = JSON.parse(node_fs_1.default.readFileSync(this.filePath, "utf-8"));
            this.ids = Array.isArray(raw) ? raw.filter((item) => typeof item === "string") : [];
        }
        catch {
            // Arquivo ausente/corrompido = ledger vazio (nunca derruba o worker).
            this.ids = [];
        }
    }
    persist() {
        if (!this.filePath)
            return;
        try {
            node_fs_1.default.mkdirSync(node_path_1.default.dirname(this.filePath), { recursive: true });
            node_fs_1.default.writeFileSync(this.filePath, JSON.stringify(this.ids), "utf-8");
        }
        catch {
            /* disco é otimização: sem o arquivo o worker apenas perde a memória */
        }
    }
}
exports.PrintedJobLedger = PrintedJobLedger;
//# sourceMappingURL=printed-jobs.js.map
