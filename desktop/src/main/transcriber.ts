// @ts-nocheck
"use strict";
/**
 * Transcrição de áudio (WhatsApp) via CLI whisper — mesmo contrato do backend
 * (app/infrastructure/audio/whisper_provider.py): binário no PATH (ou caminho
 * configurado em Settings), flags --model/--language/--output_format txt.
 *
 * Suporta tanto o CLI do openai-whisper quanto o whisper.cpp
 * (whisper-cli / main.exe): os flags usados são compatíveis com ambos
 * (--model, --language, --output_format, --output_dir, --task).
 * Falhas viram { text: "", error } — nunca exceção para o chamador.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.WhisperTranscriber = void 0;
const node_child_process_1 = require("node:child_process");
const fs = __importStar(require("node:fs"));
const os = __importStar(require("node:os"));
const path = __importStar(require("node:path"));
class WhisperTranscriber {
    executable;
    model;
    timeoutMs;
    spawnFn;
    cachedHealth = null;
    constructor(deps) {
        this.executable = deps.executable;
        this.model = deps.model;
        this.timeoutMs = deps.timeoutMs ?? 300_000;
        this.spawnFn = deps.spawnFn ?? node_child_process_1.spawn;
    }
    /** Binário presente e respondendo a --help (cacheado). */
    async health() {
        if (this.cachedHealth !== null)
            return this.cachedHealth;
        try {
            const child = this.spawnFn(this.executable, ["--help"], { windowsHide: true });
            let settled = false;
            const ok = await new Promise((resolve) => {
                const timer = setTimeout(() => {
                    if (!settled) {
                        settled = true;
                        child.kill();
                        resolve(false);
                    }
                }, 10_000);
                child.on("error", () => {
                    if (!settled) {
                        settled = true;
                        clearTimeout(timer);
                        resolve(false);
                    }
                });
                child.on("close", (code) => {
                    if (!settled) {
                        settled = true;
                        clearTimeout(timer);
                        resolve(code === 0);
                    }
                });
            });
            this.cachedHealth = ok;
            return ok;
        }
        catch {
            this.cachedHealth = false;
            return false;
        }
    }
    /** Transcreve um arquivo de áudio (wav/mp3/ogg/m4a — o que o CLI aceitar). */
    async transcribeFile(filePath, language = "pt") {
        if (!fs.existsSync(filePath)) {
            return { text: "", error: `arquivo não encontrado: ${filePath}` };
        }
        const available = await this.health();
        if (!available) {
            return {
                text: "",
                error: `whisper indisponível (executável "${this.executable}"). ` +
                    "Instale whisper.cpp e aponte o executável em Configurações.",
            };
        }
        const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "gasflow-desktop-"));
        const args = [
            filePath,
            "--model",
            this.model,
            "--language",
            language,
            "--output_format",
            "txt",
            "--output_dir",
            tmpDir,
            "--task",
            "transcribe",
        ];
        try {
            const child = this.spawnFn(this.executable, args, { windowsHide: true });
            let stdout = "";
            let stderr = "";
            child.stdout?.on("data", (d) => (stdout += d.toString()));
            child.stderr?.on("data", (d) => (stderr += d.toString()));
            const exitCode = await new Promise((resolve, reject) => {
                const timer = setTimeout(() => {
                    child.kill();
                    reject(new Error("timeout na transcrição (5 min)"));
                }, this.timeoutMs);
                child.on("error", (e) => {
                    clearTimeout(timer);
                    reject(e);
                });
                child.on("close", (code) => {
                    clearTimeout(timer);
                    resolve(code);
                });
            });
            if (exitCode !== 0) {
                return { text: "", error: `whisper exit ${exitCode}: ${stderr.slice(0, 300) || stdout.slice(0, 300)}` };
            }
            // CLI grava <stem>.txt no output_dir; usa stdout como fallback (-nt).
            const stem = path.basename(filePath, path.extname(filePath));
            const txtPath = path.join(tmpDir, `${stem}.txt`);
            let text = "";
            if (fs.existsSync(txtPath))
                text = fs.readFileSync(txtPath, "utf-8").trim();
            if (!text)
                text = stdout.trim();
            if (!text)
                return { text: "", error: "transcrição vazia (áudio sem fala?)" };
            return { text };
        }
        catch (e) {
            return { text: "", error: `falha na transcrição: ${e.message}` };
        }
        finally {
            fs.rmSync(tmpDir, { recursive: true, force: true });
        }
    }
}
exports.WhisperTranscriber = WhisperTranscriber;
//# sourceMappingURL=transcriber.js.map
