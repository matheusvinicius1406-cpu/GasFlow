// @ts-nocheck
"use strict";
/**
 * ai-setup — Item 3: IA funcionando no primeiro boot, sem o dono configurar nada.
 *
 * Fluxo (fire-and-forget — NUNCA bloqueia o boot do app):
 *   1. Detecta o Ollama (PATH + C:\Program Files\Ollama + LocalAppData).
 *   2. Se não instalado → pergunta ao dono ("Preparar IA local? ~800MB, uma vez só").
 *      Sem consentimento → marca "skipped" e não insiste mais (fallback: nenhum,
 *      cenário B da Fase 4.2 — a IA só degrada com mensagem controlada).
 *   3. Se instalado → GET /api/tags verifica o modelo; ausente → POST /api/pull
 *      com progresso via IPC (ai:download-progress).
 *   4. Persiste status em settings.json (chave "ai") e emite ai:status-changed.
 *
 * Regras do prompt (3.1): nunca bloquear o boot; nunca instalar sem
 * consentimento explícito; retry 3x com backoff; timeout de 120s por
 * request HTTP; health check com timeout curto (2s).
 */

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const os = require("node:os");

const OLLAMA_PORT = 11434;
const HEALTH_TIMEOUT_MS = 2_000;
const REQUEST_TIMEOUT_MS = 120_000;
const PULL_TIMEOUT_MS = 60 * 60_000; // download de modelo pode demorar
const INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe";
const MAX_RETRIES = 3;

/** Caminhos usuais de instalação do Ollama no Windows (ordem de prioridade). */
function candidateOllamaPaths() {
    const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
    return [
        "C:\\Program Files\\Ollama\\ollama.exe",
        path.join(localAppData, "Programs", "Ollama", "ollama.exe"),
        path.join(localAppData, "Ollama", "ollama.exe"),
    ];
}

/** true se o binário existe em PATH ou nos caminhos de instalação usuais. */
function findOllamaBinary(fsMod, existsFile, candidates) {
    void fsMod; // assinatura estável p/ testes
    for (const candidate of candidates ?? candidateOllamaPaths()) {
        try {
            if (existsFile(candidate)) return candidate;
        } catch { /* ignora */ }
    }
    return null;
}

/** GET /api/tags com timeout curto — Ollama está respondendo? */
function fetchTags(baseUrl, timeoutMs) {
    return new Promise((resolve) => {
        let settled = false;
        const done = (ok, models) => {
            if (settled) return;
            settled = true;
            resolve(ok ? { ok: true, models: models || [] } : { ok: false, models: [] });
        };
        try {
            const req = http.request(`${baseUrl}/api/tags`, { method: "GET", agent: false }, (res) => {
                let body = "";
                res.setEncoding("utf8");
                res.on("data", (chunk) => (body += chunk));
                res.on("end", () => {
                    try {
                        const parsed = JSON.parse(body);
                        done(res.statusCode === 200, (parsed.models || []).map((m) => m.name || ""));
                    } catch {
                        done(false);
                    }
                });
            });
            req.setTimeout(timeoutMs, () => {
                req.destroy();
                done(false);
            });
            req.on("error", () => done(false));
            req.end();
        } catch {
            done(false);
        }
    });
}

/**
 * AiSetupRunner — orquestra detecção/pull/status. Injeções (fs, httpFetch,
 * spawnProcess, notifyOwner) existem para os testes (sem Electron/HTTP real).
 */
class AiSetupRunner {
    constructor(deps) {
        this.deps = deps;
        this.baseUrl = deps.baseUrl || `http://127.0.0.1:${OLLAMA_PORT}`;
        this.modelName = deps.modelName || "qwen3:0.6b";
        this.fsMod = deps.fsModule || fs;
        this.httpMod = deps.httpModule || http;
        this.fetchTagsFn = deps.fetchTags || fetchTags;
        this.spawnFn = deps.spawnProcess || spawn;
        this.notifyOwner = deps.notifyOwner || null; // dialog.showMessageBox
        this.onProgress = deps.onProgress || null; // IPC ai:download-progress
        this.onStatusChanged = deps.onStatusChanged || null; // IPC ai:status-changed
        this.saveState = deps.saveState || null; // persistência em settings.json
        this.installOllamaFn = deps.installOllama || null; // sobreponível em testes
        this.sleep = deps.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
        this.existsFile = deps.existsFile || ((p) => this.fsMod.existsSync(p));
        this.status = { state: "detecting", installed: false, modelReady: false, modelName: this.modelName, lastCheck: null };
        this.pullActive = false;
    }

    /** Snapshot do status — persistido pelo index.ts via saveState. */
    getStatus() {
        return { ...this.status, lastCheck: new Date().toISOString() };
    }

    setStatus(patch) {
        this.status = { ...this.status, ...patch, lastCheck: new Date().toISOString() };
        if (this.saveState) this.saveState(this.getStatus());
        if (this.onStatusChanged) this.onStatusChanged(this.getStatus());
    }

    /** Health check + estado do modelo. Retorna o novo estado do runner. */
    async check() {
        const tags = await this.fetchTagsFn(this.baseUrl, HEALTH_TIMEOUT_MS);
        if (!tags.ok) {
            this.setStatus({ state: "unavailable" });
            return this.status;
        }
        const modelReady = tags.models.some((name) => name.startsWith(this.modelName));
        this.setStatus({ state: modelReady ? "ready" : "preparing", installed: true, modelReady });
        return this.status;
    }

    /**
     * Fluxo completo do boot (chamar com void — nunca await no boot).
     * Detecta → (consentimento p/ instalar) → pull se necessário → status final.
     * NUNCA lança: qualquer erro vira estado "unavailable" (o boot do app
     * não pode ser afetado pela IA em hipótese alguma).
     */
    async run() {
        try {
            return await this.runInner();
        } catch {
            this.setStatus({ state: "unavailable" });
            return this.status;
        }
    }

    async runInner() {
        const binary = findOllamaBinary(this.fsMod, this.existsFile, this.deps.candidates);
        if (!binary) {
            const accepted = await this.promptInstallConsent();
            if (!accepted) {
                this.setStatus({ state: "skipped", installed: false, modelReady: false });
                return this.status;
            }
            const installed = this.installOllamaFn
                ? await this.installOllamaFn()
                : await this.installOllamaWithRetry();
            if (!installed) {
                this.setStatus({ state: "unavailable", installed: false, modelReady: false });
                return this.status;
            }
        }
        else {
            this.setStatus({ installed: true });
        }
        await this.check();
        if (this.status.state === "ready") return this.status;
        if (this.status.state === "unavailable") return this.status; // instalado mas não respondeu
        await this.pullModel(this.modelName);
        return this.status;
    }

    /** Pergunta ao dono antes de qualquer download de instalador. */
    async promptInstallConsent() {
        if (!this.notifyOwner) return false; // sem diálogo → nunca instala
        try {
            return await this.notifyOwner({
                title: "GasFlow",
                message: "Preparar IA local?\n\nBaixa ~800 MB uma única vez. O app funciona normalmente mesmo sem isso.",
                buttons: ["Baixar agora", "Agora não"],
                defaultId: 0,
                cancelId: 1,
            });
        } catch {
            return false;
        }
    }

    /** Baixa e roda o instalador silenciosamente (3 tentativas, backoff). */
    async installOllamaWithRetry() {
        for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
            try {
                await this.installOllamaOnce();
                return true;
            } catch (e) {
                if (attempt === MAX_RETRIES) return false;
                await this.sleep(1000 * Math.pow(2, attempt - 1));
            }
        }
        return false;
    }

    /** Uma tentativa: download HTTP do instalador + execução silenciosa. */
    async installOllamaOnce() {
        const tmpInstaller = path.join(os.tmpdir(), "OllamaSetup.exe");
        await this.downloadFile(INSTALLER_URL, tmpInstaller, () => undefined);
        await new Promise((resolve, reject) => {
            const child = this.spawnFn(tmpInstaller, ["/verysilent", "/norestart"], { detached: false, stdio: "ignore" });
            child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`instalador saiu com código ${code}`))));
            child.on("error", reject);
        });
    }

    /** POST /api/pull com progresso. 3 tentativas com backoff. */
    async pullModel(model) {
        this.pullActive = true;
        this.setStatus({ state: "preparing", modelReady: false });
        try {
            for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
                const ok = await this.pullOnce(model);
                if (ok) {
                    await this.check();
                    return true;
                }
                if (attempt < MAX_RETRIES) await this.sleep(1000 * Math.pow(2, attempt - 1));
            }
            this.setStatus({ state: "unavailable", modelReady: false });
            return false;
        }
        finally {
            this.pullActive = false;
        }
    }

    /** Uma tentativa de pull; devolve true quando completou. */
    async pullOnce(model) {
        const body = JSON.stringify({ name: model });
        return new Promise((resolve) => {
            let settled = false;
            const finish = (ok) => {
                if (settled) return;
                settled = true;
                resolve(ok);
            };
            let lastPercent = 0;
            const req = this.httpMod.request(`${this.baseUrl}/api/pull`, {
                method: "POST",
                agent: false,
                headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
            }, (res) => {
                if (res.statusCode !== 200) {
                    if (typeof res.resume === "function") res.resume();
                    finish(false);
                    return;
                }
                res.setEncoding("utf8");
                res.on("data", (chunk) => {
                    for (const line of chunk.split("\n")) {
                        if (!line.trim()) continue;
                        try {
                            const evt = JSON.parse(line);
                            const total = evt.total || 0;
                            const done = evt.completed || 0;
                            if (total > 0) lastPercent = Math.min(99, Math.round((done * 100) / total));
                            if (evt.error) {
                                finish(false);
                                return;
                            }
                            if (this.onProgress) this.onProgress({ percent: lastPercent, bytes: done, total });
                        } catch { /* linha parcial — ignora */ }
                    }
                });
                res.on("end", () => {
                    if (this.onProgress) this.onProgress({ percent: 100, bytes: 0, total: 0 });
                    finish(true);
                });
            });
            req.setTimeout(PULL_TIMEOUT_MS, () => {
                req.destroy();
                finish(false);
            });
            req.on("error", () => finish(false));
            req.write(body);
            req.end();
        });
    }

    /** Download HTTP genérico com progresso e timeout de 120s por request. */
    async downloadFile(url, dest, onProgress) {
        return new Promise((resolve, reject) => {
            const req = http.get(url, { agent: false }, (res) => {
                if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                    res.resume();
                    this.downloadFile(res.headers.location, dest, onProgress).then(resolve, reject);
                    return;
                }
                if (res.statusCode !== 200) {
                    res.resume();
                    reject(new Error(`download HTTP ${res.statusCode}`));
                    return;
                }
                const total = Number.parseInt(res.headers["content-length"] || "0", 10);
                const file = this.fsMod.createWriteStream(dest);
                let received = 0;
                res.on("data", (chunk) => {
                    received += chunk.length;
                    if (total) onProgress(Math.round((received * 100) / total));
                });
                res.pipe(file);
                file.on("finish", () => file.close());
                file.on("close", () => resolve());
                file.on("error", reject);
            });
            req.setTimeout(REQUEST_TIMEOUT_MS, () => {
                req.destroy(new Error("timeout no download do instalador"));
            });
            req.on("error", reject);
        });
    }
}

/** Estado persistido em settings.json (merge suave — preserva chaves existentes). */
function mergeAiState(settings, aiState) {
    return { ...(settings || {}), ai: { ...((settings && settings.ai) || {}), ...aiState } };
}

Object.defineProperty(exports, "__esModule", { value: true });
exports.AiSetupRunner = AiSetupRunner;
exports.mergeAiState = mergeAiState;
exports.candidateOllamaPaths = candidateOllamaPaths;
exports.findOllamaBinary = findOllamaBinary;
exports.fetchTags = fetchTags;
exports.OLLAMA_PORT = OLLAMA_PORT;
